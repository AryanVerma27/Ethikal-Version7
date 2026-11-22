"""Placement-oriented Mech Royale bot for the mechfight/1 protocol."""

from math import asin, atan2, cos, dist, hypot, pi, remainder, sin, sqrt

from arena_model import Arena
import mechfight


WEAPON_PROFILES = {
    "lightning": {"mortar": 2, "laser": 1, "lightning": 4},
    "mortar": {"mortar": 4, "laser": 1, "lightning": 2},
    "laser": {"mortar": 2, "laser": 4, "lightning": 1},
}
UPGRADE_VALUE = {
    "armor": 15, "servos": 14, "nanites": 13, "plating": 12,
    "gun_damage": 10, "reactor": 9, "lightning_range": 9, "gun_rate": 8,
    "jets": 8, "laser_damage": 8, "mortar_reload": 8, "gyros": 7,
    "capacitor": 6, "gun_mag": 6, "sensors": 5, "lightning_efficiency": 5,
}


def unit(x, y):
    length = hypot(x, y)
    return (x / length, y / length) if length else (0, 0)


def angles(dx, dy, dz):
    return atan2(dy, dx), atan2(dz, hypot(dx, dy))


def distance(a, b):
    return hypot(a[0] - b[0], a[1] - b[1])


class Bot:
    name = "Oval Warden Ascend"

    def __init__(self, hello, profile="adaptive"):
        self.arena = Arena(hello["map"]["dir"])
        self.config = hello["config"]
        self.last_hit = -100
        self.bearing = None
        self.turn = 1 if hello["seed"] % 2 else -1
        self.heading = None
        self.anchor = None
        self.anchor_time = 0
        self.stuck_until = 0
        self.goal_id = None
        self.scout_goal = None
        self.scout_until = 0
        self.detour_path = []
        self.detour_goal = None
        self.detour_until = 0
        self.next_search = 0
        self.profile = profile
        self.target_id = None
        self.recover_until = 0

    def safe(self, pos, zone, remaining, speed):
        excess = distance(pos, zone["next_center"]) - max(0, zone["next_radius"] - 8)
        return excess <= max(0, remaining - 17) * speed * 0.45

    def movement(self, obs, goal, threats, retreat, urgent, capture, sprint=False):
        me, zone = obs["self"], obs["zone"]
        x, y, z = me["pos"]
        stats = me["stats"]
        gx, gy = goal[:2]
        gap = distance((x, y), (gx, gy))
        t = obs["t"]
        incoming = []
        for projectile in obs["projectiles"]:
            px, py, pz = projectile["pos"]
            vx, vy, _ = projectile["vel"]
            v2 = vx * vx + vy * vy
            if not v2 or abs(pz - z - stats["height"] / 2) > stats["height"]:
                continue
            eta = ((x - px) * vx + (y - py) * vy) / v2
            if 0 < eta < .45 and hypot(x - px - eta * vx, y - py - eta * vy) < 9:
                incoming.append((px + eta * vx, py + eta * vy, eta))
                if len(incoming) == 5:
                    break
        if self.anchor is None:
            self.anchor, self.anchor_time = (x, y), t
        if t - self.anchor_time >= 1.3:
            if gap > 8 and distance(self.anchor, (x, y)) < 3:
                self.turn *= -1
                self.stuck_until = t + 1.6
            self.anchor, self.anchor_time = (x, y), t

        if capture and gap < 3 and not urgent:
            return (0, 0), False, False

        if self.detour_path and (t >= self.detour_until or distance(goal, self.detour_goal) > 16
                                 or retreat or not me["grounded"]):
            self.detour_path.clear()
        if me["grounded"] and gap > 12 and not retreat and not self.detour_path and t >= self.next_search:
            dx, dy = unit(gx - x, gy - y)
            length = min(10, gap)
            if t < self.stuck_until or not self.arena.walkable(x + dx * length, y + dy * length, z, stats):
                self.next_search = t + .8
                route = self.arena.detour(me["pos"], goal, stats, self.turn)
                if route:
                    self.detour_path, self.detour_goal, self.detour_until = route, goal, t + 5
        while self.detour_path and distance((x, y), self.detour_path[-1]) < 3:
            self.detour_path.pop()
        following_detour = bool(self.detour_path)
        if following_detour:
            gx, gy = goal = self.detour_path[-1]
            gap = distance((x, y), goal)

        preferred = atan2(gy - y, gx - x)
        stride = min(12, max(3, gap))
        best = None
        pursuers = [e for e in threats[:2] if distance((x, y), e["pos"]) < 65]
        for offset in (0, .30, -.30, .64, -.64, 1.0, -1.0, 1.42, -1.42, 1.91, -1.91, 2.46, -2.46, pi):
            yaw = preferred + offset * self.turn
            ux, uy = cos(yaw), sin(yaw)
            reach = 0
            feet = z
            for step in (2, 5, 8, 12):
                step = min(step, stride)
                px, py = x + step * ux, y + step * uy
                if not self.arena.walkable(px, py, feet, stats):
                    break
                reach = step
                ground = self.arena.ground(px, py)
                if me["grounded"] and feet - ground < 2.0:
                    feet = ground
                if step >= stride:
                    break

            if not reach:
                continue
            end = x + reach * ux, y + reach * uy
            score = gap - distance(end, goal) + 0.4 * reach
            for px, py, eta in incoming:
                travel = min(reach, stats["walk_speed"] * eta)
                clearance = hypot(x + travel * ux - px, y + travel * uy - py)
                score -= 1.5 * max(0, stats["radius"] + 2 - clearance)
            if me["in_zone"]:
                score -= 3 * max(0, distance(end, zone["center"]) - zone["radius"] + 2)
            if urgent and not following_detour:
                score += 1.7 * (distance((x, y), zone["center"]) - distance(end, zone["center"]))
            if self.heading is not None:
                score += (4 if t < self.stuck_until else 2) * cos(yaw - self.heading)
            for enemy in threats[:3]:
                epos = enemy["pos"]
                change = distance(end, epos) - distance((x, y), epos)
                if retreat:
                    score += 0.8 * change
                elif distance((x, y), epos) < 24:
                    score += 0.4 * change
            if retreat and reach >= 5:
                for enemy in pursuers:
                    ex, ey, ez = enemy["pos"]
                    if not self.arena.clear((ex, ey, ez + 7), (*end, feet + 4.5)):
                        score += 9
            score -= .03 * abs(offset)
            if best is None or score > best[0]:
                best = score, ux, uy, yaw, reach

        energy = me["energy"]
        jet = False
        if best is None:
            ux, uy = unit(gx - x, gy - y)
            jet = energy > 18
        else:
            _, ux, uy, self.heading, reach = best
            if gap < 7 and not urgent:
                scale = min(1, gap / 5)
                ux, uy = ux * scale, uy * scale
            jet = not following_detour and energy > 25 and (reach < 5 and gap > 12 or t < self.stuck_until)
        if not me["grounded"]:
            jet = energy > 12 and (
                jet or (me["vel"][2] > 0 and energy > 42
                        and not self.arena.walkable(x + 7 * ux, y + 7 * uy, z, stats))
            )
        boost = jet or (me["grounded"] and gap > 18 and (
            urgent and energy > 12 or retreat and energy > 32 or sprint and energy > 56
        ))
        return (ux, uy), boost, jet and me["grounded"]

    def weapon_values(self, obs, opponent):
        if self.profile != "adaptive":
            return WEAPON_PROFILES[self.profile]
        # Keep the close-range double trigger unless the fight favors ranged burst.
        if opponent:
            weapons = opponent.get("weapons", ())
            gap = distance(obs["self"]["pos"], opponent["pos"])
            if "mortar" in weapons and gap > 50:
                return WEAPON_PROFILES["laser"]
            if "lightning" in weapons and gap > 30:
                return WEAPON_PROFILES["mortar"]
        if obs["alive"] > 11 and obs["t"] < 110 and obs["self"]["energy"] < 35:
            return WEAPON_PROFILES["mortar"]
        return WEAPON_PROFILES["lightning"]

    def shot(self, me, target, weapon):
        stats = weapon["stats"]
        kind = weapon["kind"]
        pos = target["pos"]
        vel = target.get("vel", (0, 0, 0))
        npc = target.get("kind") == "npc"
        crate = target["id"] >= 1000
        size = 1 + self.config["cubes"]["size_per_cube"] * target.get("cubes", 0)
        height = 1.8 if npc else self.config["crates"]["height"] / 2 if crate else 4.5 * size
        radius = 1.8 if npc else self.config["crates"]["radius"] if crate else self.config["mech"]["radius"] * size
        x, y, z = me["pos"]
        muzzle = me["stats"]["muzzle_height"]
        if kind == "mortar":
            muzzle = me["stats"]["height"] + .5
        origin = (x, y, z + muzzle)
        d = dist(origin, (pos[0], pos[1], pos[2] + height))
        if kind == "mortar":
            if not 12 < d < min(145, stats["speed"] ** 2 / stats["gravity"] * .68):
                return None
        elif d > stats["range"]:
            return None

        flight = 0
        if kind in ("gun", "mortar"):
            flight = max(0, d - me["stats"]["radius"] - .5) / stats["speed"]
        for _ in range(3):
            lead = min(flight + .05, 1.65)
            endpoint = (pos[0] + vel[0] * lead, pos[1] + vel[1] * lead,
                        max(self.arena.ground(pos[0], pos[1]), pos[2] + vel[2] * min(lead, .25)) + height)
            gravity = stats["gravity"] if kind == "mortar" else 0
            rise = .5 * gravity * flight ** 2
            delta = (endpoint[0] - x, endpoint[1] - y, endpoint[2] - origin[2] + rise)
            if kind in ("gun", "mortar"):
                flight = max(0, hypot(*delta) - me["stats"]["radius"] - .5) / stats["speed"]
        yaw, pitch = angles(*delta)
        limits = me["stats"]
        if not limits["min_pitch"] <= pitch <= limits["max_pitch"]:
            return None
        if not self.arena.clear(origin, endpoint, rise):
            return None
        tolerance = asin(min(.95, radius / max(1, d))) * .9
        if kind == "lightning":
            tolerance = stats["cone_deg"] * pi / 360 * .85
        return yaw, pitch, tolerance

    def act(self, obs):
        t, zone, me = obs["t"], obs["zone"], obs["self"]
        pos = me["pos"]
        action = {"tick": obs["tick"]}
        if obs["offer"]:
            choices = obs["offer"]["choices"]
            action["pick"] = max(range(len(choices)), key=lambda i: UPGRADE_VALUE.get(choices[i]["id"], 3))
        for event in obs["events"]:
            if event["type"] == "damaged" and event.get("bearing") is not None:
                self.last_hit, self.bearing = t, event["bearing"]

        enemies = sorted((e for e in obs["mechs"] if e["kind"] == "mech"),
                         key=lambda e: distance(pos, e["pos"]))
        threats = [e for e in enemies if distance(pos, e["pos"]) < 105]
        drones = [e for e in obs["mechs"] if e["kind"] == "npc"]
        hp = me["hp"] / me["max_hp"]
        close = sum(distance(pos, e["pos"]) < 70 for e in threats)
        opponent = threats[0] if threats else None
        gun, secondary = me["weapons"]
        special = secondary["kind"] if secondary else None
        opponent_hp = opponent.get("hp", 1400) if opponent else 1400
        fight_advantage = me["hp"] >= opponent_hp * 1.35 and (
            special is not None or me["cubes"] >= 3
        )
        finish = bool(opponent and close <= 1 and distance(pos, opponent["pos"]) < 77
                      and opponent_hp < min(555 if special else 360, me["hp"] * .52))
        recently_hit = t - self.last_hit < 4
        if close >= 3 or close >= 2 and hp < .77 or hp < .50 and (threats or recently_hit):
            self.recover_until = t + 1.4
        retreat = not finish and t < self.recover_until and (bool(threats) or recently_hit)
        time_left = zone["shrink_end"] - t
        speed = me["stats"]["walk_speed"]
        next_gap = distance(pos, zone["next_center"])
        urgent = not me["in_zone"] or not self.safe(pos, zone, time_left, speed)
        if zone["next_radius"] == 0:
            urgent = not me["in_zone"] or next_gap > max(1.5, min(zone["radius"] - 7, time_left * .65))

        values = self.weapon_values(obs, opponent)
        current = values.get(special, 0)
        pickups = []
        best_take = current
        for pickup in obs["pickups"]:
            value = values.get(pickup["kind"], 0)
            if value <= current or abs(pickup["pos"][2] - pos[2]) > 4:
                continue
            d = distance(pos, pickup["pos"])
            if d <= self.config["loot"]["pickup_radius"] and not (secondary and secondary.get("charge", 0)):
                if value > best_take and (not secondary or not close or value - current >= 2):
                    best_take = value
                    action["take"] = pickup["id"]
                    if secondary:
                        action["drop"] = 1
            else:
                pickups.append((value, pickup))

        goal = zone["next_center"] if urgent else pos
        farming_target = None
        capture = False
        candidates = []
        if not urgent and not retreat:
            for value, p in pickups:
                candidates.append((40 + 9 * value + (18 if not secondary else 0), p, False))
            for cube in obs["cubes"]:
                candidates.append((88 if me["cubes"] < 10 else 44, cube, False))
            if not close and t - self.last_hit > 3 and me["cubes"] < 10:
                for crate in obs["crates"]:
                    candidates.append((49 + (1 - crate["hp"] / self.config["crates"]["hp"]) * 23, crate, False))
                for drone in drones:
                    candidates.append((60 + (1 - drone["hp"] / drone["max_hp"]) * 26, drone, False))
        if not urgent:
            for drop in obs["drops"]:
                d = distance(pos, drop["pos"])
                if (drop["holder"] in (None, me["id"]) and drop["lands_in"] < d / speed + 4
                        and (not retreat or not close and not recently_hit)):
                    candidates.append((130 + 120 * (1 - hp), drop, True))

        ranked = []
        for value, item, is_drop in candidates:
            dest = item["pos"]
            d = distance(pos, dest)
            if abs(dest[2] - pos[2]) > 5 or not self.safe(dest, zone, time_left, speed):
                continue
            if distance(dest, zone["center"]) >= zone["radius"] - 2:
                continue
            if any(distance(dest, e["pos"]) < 32 for e in threats):
                continue
            score = value - d + (9 if item["id"] == self.goal_id else 0)
            if finish and not is_drop:
                score -= 30
            if is_drop and item["holder"] == me["id"]:
                score += 80
            if score > 0:
                ranked.append((score, item, is_drop))
        if ranked:
            _, item, capture = max(ranked, key=lambda entry: entry[0])
            self.goal_id = item["id"]
            goal = item["pos"]
            if 100 <= item["id"] < 5000:
                farming_target = item
                if distance(pos, goal) < 12:
                    goal = pos
        else:
            self.goal_id = None
            if retreat and not urgent:
                if threats:
                    ax = ay = 0
                    for enemy in threats[:4]:
                        dx, dy = unit(pos[0] - enemy["pos"][0], pos[1] - enemy["pos"][1])
                        weight = 1 / max(10, distance(pos, enemy["pos"]))
                        ax, ay = ax + dx * weight, ay + dy * weight
                    dx, dy = unit(ax, ay)
                else:
                    dx, dy = -cos(self.bearing), -sin(self.bearing)
                goal = (pos[0] + 42 * dx, pos[1] + 42 * dy)
                if distance(goal, zone["center"]) > zone["radius"] - 10:
                    goal = zone["next_center"]
            elif threats and not urgent:
                enemy = opponent["pos"]
                d = distance(pos, enemy)
                bx, by = unit(pos[0] - enemy[0], pos[1] - enemy[1])
                ideal = {"lightning": 29, "mortar": 39, "laser": 61}.get(special, 48)
                if "lightning" in opponent.get("weapons", ()) and special != "lightning":
                    ideal = max(ideal, 47)
                if finish:
                    ideal = min(ideal, 24)
                radial = max(-1.5, min(1, (ideal - d) / 20))
                strafe = self.turn if int(t / 1.35) % 2 else -self.turn
                if d > ideal + 10 and (finish or close <= 1 and fight_advantage):
                    strafe *= .6
                goal = (pos[0] + 22 * (radial * bx - strafe * by),
                        pos[1] + 22 * (radial * by + strafe * bx))
            elif hp >= .80 and me["cubes"] < 6 and t < 150 and not urgent and t - self.last_hit > 6:
                if self.scout_goal is None or self.scout_until < t or distance(pos, self.scout_goal) < 10:
                    inward = atan2(zone["next_center"][1] - pos[1], zone["next_center"][0] - pos[0])
                    for offset in (.75, -.75, 1.6, -1.6, 0):
                        yaw = inward + self.turn * offset
                        candidate = (pos[0] + 58 * cos(yaw), pos[1] + 58 * sin(yaw))
                        if (distance(candidate, zone["center"]) < zone["radius"] - 15
                                and self.safe(candidate, zone, time_left, speed)
                                and self.arena.walkable(*candidate, self.arena.ground(*candidate), me["stats"])):
                            self.scout_goal, self.scout_until = candidate, t + 6
                            break
                if self.scout_goal and self.scout_until >= t:
                    goal = self.scout_goal

        if distance(pos, goal) > 1:
            sprint = capture or finish or (not close and farming_target is None and self.goal_id is not None)
            move, boost, jump = self.movement(obs, goal, threats, retreat, urgent, capture, sprint)
            action.update(move=move, boost=boost, jump=jump)
        else:
            action["move"] = (0, 0)

        engage_range = 88 if obs["alive"] > 7 else 150
        if recently_hit:
            engage_range += 45
        targets = sorted((e for e in enemies if distance(pos, e["pos"]) <= engage_range),
                         key=lambda e: distance(pos, e["pos"]) + .075 * e.get("hp", 1400)
                         - (10 if e["id"] == self.target_id else 0))[:3]
        if not retreat and (hp > .42 or t - self.last_hit < 2):
            if farming_target:
                targets.append(farming_target)
            targets.extend(d for d in drones[:3] if distance(pos, d["pos"]) < 43 and d != farming_target)
        if retreat:
            # Stop resetting the regeneration timer when safely creating distance.
            targets = [e for e in targets if distance(pos, e["pos"]) < 32 or e.get("hp", 1400) < 160]
        fire = [False, False]
        shot_found = False
        self.target_id = None
        for target in targets:
            gun_shot = self.shot(me, target, gun)
            charging = secondary.get("charge", 0) if secondary else 0
            ready = secondary and secondary["cooldown"] <= .095
            special_shot = self.shot(me, target, secondary) if ready or charging else None
            use_special = special_shot and (
                charging or ready and (
                    special == "mortar" or special == "laser" and not retreat and not urgent
                    or special == "lightning" and me["energy"] > secondary["stats"]["energy"] + 8
                )
            )
            if use_special and special == "mortar" and gun_shot and gun["ammo"] > 0:
                use_special = target.get("hp", 1400) > gun["stats"]["damage"] * .75
            if use_special and special == "laser" and not charging and gun_shot and gun["ammo"] > 0:
                use_special = target.get("hp", 1400) > gun["stats"]["damage"]
            aim = special_shot if use_special else gun_shot
            if (use_special and special == "lightning" and gun_shot
                    and abs(remainder(special_shot[0] - gun_shot[0], 2 * pi)) < special_shot[2] * .65):
                aim = gun_shot
            if aim is None:
                continue
            yaw, pitch, tolerance = aim
            action["aim"] = (yaw, pitch)
            self.target_id = target["id"]
            shot_found = True
            yaw_error = abs(remainder(yaw - me["aim"][0], 2 * pi))
            pitch_error = abs(pitch - me["aim"][1])
            aligned = yaw_error < tolerance + me["stats"]["turn_rate"] * .045 and (
                use_special and special == "lightning"
                or pitch_error < tolerance + me["stats"]["pitch_rate"] * .045
            )
            if use_special:
                if special == "laser":
                    charge_goal = secondary["stats"]["charge"]
                    if target.get("hp", 1400) < secondary["stats"]["damage"] * .6:
                        charge_goal = secondary["stats"]["min_charge"] + .1
                    fire[1] = not (aligned and charging >= charge_goal - .04)
                else:
                    fire[1] = aligned
            if gun_shot:
                gun_yaw, gun_pitch, gun_tolerance = gun_shot
                fire[0] = (
                    abs(remainder(gun_yaw - yaw, 2 * pi)) < gun_tolerance
                    and abs(gun_pitch - pitch) < gun_tolerance
                    and hypot(
                        max(0, abs(remainder(gun_yaw - me["aim"][0], 2 * pi))
                            - me["stats"]["turn_rate"] * .05) * cos(gun_pitch),
                        max(0, abs(gun_pitch - me["aim"][1]) - me["stats"]["pitch_rate"] * .05),
                    ) < gun_tolerance
                )
            break
        if not shot_found:
            if t - self.last_hit < 2:
                yaw = self.bearing
            elif threats:
                yaw = atan2(threats[0]["pos"][1] - pos[1], threats[0]["pos"][0] - pos[0])
            elif distance(pos, goal) > 2:
                yaw = atan2(goal[1] - pos[1], goal[0] - pos[0])
            else:
                yaw = remainder(t * .85, 2 * pi)
            action["aim"] = (yaw, 0)
            if gun["ammo"] < gun["stats"]["mag"] * .68 and gun["reload"] == 0:
                action["reload"] = True
        elif retreat and gun["ammo"] <= 2 and gun["reload"] == 0 and not fire[0]:
            action["reload"] = True
        action["fire"] = fire
        return action


if __name__ == "__main__":
    mechfight.run(Bot)
