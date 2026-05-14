"""
Generate a **bounded Forge 1.20.1-style** custom mob scaffold (Java + assets + docs).

Merge-friendly source for an existing Forge MDK — not a runnable mod by itself.
Optional GeckoLib notes live in ``docs/GECKOLIB_NOTES.md`` inside the zip.
"""

from __future__ import annotations

import io
import json
import re
import zipfile
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any, Dict, List, Mapping, Tuple


def _mod_id_safe(s: str) -> str:
    t = (s or "").strip().lower().replace("-", "_")
    t = re.sub(r"[^a-z0-9_]", "", t)
    return t or "forager_mob"


def _java_package_safe(s: str) -> str:
    t = (s or "").strip().lower()
    t = re.sub(r"[^a-z0-9_.]", "", t)
    parts = [p for p in t.split(".") if p and p[0].isalpha()]
    return ".".join(parts) if parts else "com.forager.mobdemo.mobs"


def _class_safe(name: str) -> str:
    n = "".join(ch for ch in (name or "").strip() if ch.isalnum() or ch == "_")
    if not n or not n[0].isalpha():
        n = "CustomMob" + (n or "X")
    return n[0].upper() + n[1:]


def _reg_safe(name: str) -> str:
    n = re.sub(r"[^a-z0-9_]", "_", (name or "").strip().lower())
    return n or "custom_mob"


def load_mob_authoring_playbooks() -> List[Dict[str, Any]]:
    p = Path(__file__).resolve().parent / "data" / "mob_authoring_playbooks.json"
    if not p.is_file():
        return []
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    items = raw.get("playbooks") if isinstance(raw, dict) else None
    if not isinstance(items, list):
        return []
    return [x for x in items if isinstance(x, dict)]


ABILITY_IDS = (
    "leap_melee",
    "aoe_slam",
    "summon_on_hurt",
    "ranged_popshot",
    "phase_speed_burst",
)


@dataclass
class MobScaffoldSpec:
    mod_id: str = "forager_mobdemo"
    java_package: str = "com.forager.mobdemo.mobs"
    entity_class_name: str = "AshDrake"
    registry_name: str = ""
    display_name: str = "Ash Drake"
    mob_category: str = "MONSTER"
    hitbox_width: float = 1.6
    hitbox_height: float = 2.2
    max_health: float = 48.0
    movement_speed: float = 0.26
    attack_damage: float = 5.0
    armor: float = 2.0
    summon_cap: int = 3
    abilities: Tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        self.mod_id = _mod_id_safe(self.mod_id)
        self.java_package = _java_package_safe(self.java_package)
        self.entity_class_name = _class_safe(self.entity_class_name)
        self.registry_name = _reg_safe(self.registry_name or self.entity_class_name)
        self.mob_category = (self.mob_category or "MONSTER").strip().upper()
        self.abilities = tuple(str(a).lower() for a in self.abilities if str(a).lower() in ABILITY_IDS)


def _readme(spec: MobScaffoldSpec) -> str:
    ab = ", ".join(spec.abilities) if spec.abilities else "(none — add goals in Java)"
    return f"""# Forager mob scaffold — {spec.entity_class_name}

## What this is
- **Forge 1.20.1-oriented** Java for a **Monster** subclass plus optional **AI goals** (no GeckoLib required for this zip).
- **Not a complete mod** — merge into your MDK and register the deferred entity type on the **mod** event bus.

## Merge checklist
1. Copy ``src/`` into your Forge project.
2. In your ``@Mod`` constructor: ``{spec.entity_class_name}Entities.register(modEventBus);``
3. Attribute defaults: ``{spec.entity_class_name}EntityAttributes`` subscribes to ``EntityAttributeCreationEvent`` — ensure that class is on the classpath (same module).
4. ``gradlew runClient`` — fix **mapping** names if your MDK differs (scaffold uses common Mojang-style names).
5. Add **spawn** rules / loot tables yourself.

## Abilities baked into this zip
{ab}

## GeckoLib
See ``docs/GECKOLIB_NOTES.md``. Model in **Blockbench**; Forager does not emit meshes.

## In-game
``/summon {spec.mod_id}:{spec.registry_name} ~ ~ ~``
"""


def _gecko_notes(spec: MobScaffoldSpec) -> str:
    return f"""# GeckoLib (optional) — {spec.entity_class_name}

## Gradle (verify current artifact on Modrinth)
```gradle
repositories {{
    maven {{ url = "https://dl.cloudsmith.io/public/geckolib3/geckolib/maven/" }}
}}
dependencies {{
    implementation fg.deobf("software.bernie.geckolib:geckolib-forge-1.20.1:4.4.4")
}}
```

Wire ``GeoEntity`` + renderer after behavior compiles.
"""


def _entity_java(spec: MobScaffoldSpec) -> str:
    pkg = spec.java_package
    cls = spec.entity_class_name
    mod = spec.mod_id
    reg = spec.registry_name
    ab = {a.lower() for a in spec.abilities}

    imports = [
        "import net.minecraft.world.entity.EntityType;",
        "import net.minecraft.world.entity.ai.attributes.AttributeSupplier;",
        "import net.minecraft.world.entity.ai.attributes.Attributes;",
        "import net.minecraft.world.entity.monster.Monster;",
        "import net.minecraft.world.level.Level;",
    ]
    if "summon_on_hurt" in ab:
        imports.append("import net.minecraft.world.entity.monster.Zombie;")

    tick_method = ""
    hurt_method = ""

    if "phase_speed_burst" in ab:
        tick_method = f"""
    @Override
    public void tick() {{
        super.tick();
        if (this.level().isClientSide) {{
            return;
        }}
        int cycle = this.tickCount % 200;
        var attr = this.getAttribute(Attributes.MOVEMENT_SPEED);
        if (attr != null) {{
            if (cycle < 40) {{
                attr.setBaseValue(Math.max(MOVEMENT_SPEED, 0.42));
            }} else {{
                attr.setBaseValue(MOVEMENT_SPEED);
            }}
        }}
    }}
"""

    if "summon_on_hurt" in ab:
        cap = int(spec.summon_cap)
        hurt_method = f"""
    @Override
    public boolean hurt(net.minecraft.world.damagesource.DamageSource source, float amount) {{
        boolean ok = super.hurt(source, amount);
        if (ok && !this.level().isClientSide && this.random.nextFloat() < 0.18f && this.getTarget() != null) {{
            long nearby = this.level().getEntitiesOfClass(Zombie.class, this.getBoundingBox().inflate(10))
                .stream().filter(z -> z.getPersistentData().getBoolean("{mod}_summon")).count();
            if (nearby < {cap}) {{
                Zombie z = net.minecraft.world.entity.EntityType.ZOMBIE.create(this.level());
                if (z != null) {{
                    z.moveTo(
                        this.getX() + (this.random.nextDouble() - 0.5) * 2,
                        this.getY(),
                        this.getZ() + (this.random.nextDouble() - 0.5) * 2,
                        this.getYRot(),
                        0.0f
                    );
                    z.getPersistentData().putBoolean("{mod}_summon", true);
                    z.setBaby(true);
                    this.level().addFreshEntity(z);
                }}
            }}
        }}
        return ok;
    }}
"""

    goals: List[str] = [
        "this.goalSelector.addGoal(1, new net.minecraft.world.entity.ai.goal.FloatGoal(this));",
    ]
    if "leap_melee" in ab:
        goals.append("this.goalSelector.addGoal(3, new ForagerLeapMeleeGoal(this, 0.32f, 0.55f));")
    if "aoe_slam" in ab:
        goals.append("this.goalSelector.addGoal(3, new ForagerAoESlamGoal(this, 80, 3.2f, 6.0f));")
    if "ranged_popshot" in ab:
        goals.append("this.goalSelector.addGoal(3, new ForagerRangedPopshotGoal(this, 14, 1.1f));")
    goals.extend(
        [
            "this.goalSelector.addGoal(4, new net.minecraft.world.entity.ai.goal.MeleeAttackGoal(this, 1.1, true));",
            "this.goalSelector.addGoal(5, new net.minecraft.world.entity.ai.goal.WaterAvoidingRandomStrollGoal(this, 0.9));",
            "this.goalSelector.addGoal(6, new net.minecraft.world.entity.ai.goal.LookAtPlayerGoal(this, net.minecraft.world.entity.player.Player.class, 8));",
            "this.goalSelector.addGoal(7, new net.minecraft.world.entity.ai.goal.RandomLookAroundGoal(this));",
            "this.targetSelector.addGoal(2, new net.minecraft.world.entity.ai.goal.target.NearestAttackableTargetGoal<>(this, net.minecraft.world.entity.player.Player.class, true));",
        ]
    )
    goals_block = "\n        ".join(goals)
    import_block = "\n".join(imports)

    return f"""package {pkg};

{import_block}

/** Forager-generated mob — tune constants + goals. Registry id: ``{mod}:{reg}``. */
public class {cls} extends Monster {{
    public static final double MAX_HEALTH = {spec.max_health};
    public static final double MOVEMENT_SPEED = {spec.movement_speed};
    public static final double ATTACK_DAMAGE = {spec.attack_damage};
    public static final double ARMOR = {spec.armor};

    public {cls}(EntityType<? extends Monster> type, Level level) {{
        super(type, level);
        {goals_block}
    }}

    public static AttributeSupplier.Builder createAttributes() {{
        return Monster.createMonsterAttributes()
            .add(Attributes.MAX_HEALTH, MAX_HEALTH)
            .add(Attributes.MOVEMENT_SPEED, MOVEMENT_SPEED)
            .add(Attributes.ATTACK_DAMAGE, ATTACK_DAMAGE)
            .add(Attributes.ARMOR, ARMOR)
            .add(Attributes.FOLLOW_RANGE, 28.0);
    }}
{tick_method}{hurt_method}
}}
"""


def _registrar_java(spec: MobScaffoldSpec) -> str:
    pkg = spec.java_package
    cls = spec.entity_class_name
    mod = spec.mod_id
    reg = spec.registry_name
    cat = spec.mob_category
    return f"""package {pkg};

import net.minecraft.resources.ResourceLocation;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.entity.MobCategory;
import net.minecraft.world.entity.monster.Monster;
import net.minecraftforge.eventbus.api.IEventBus;
import net.minecraftforge.registries.DeferredRegister;
import net.minecraftforge.registries.ForgeRegistries;
import net.minecraftforge.registries.RegistryObject;

public final class {cls}Entities {{
    public static final DeferredRegister<EntityType<?>> ENTITY_TYPES =
        DeferredRegister.create(ForgeRegistries.ENTITY_TYPES, "{mod}");

    public static final RegistryObject<EntityType<{cls}>> ENTITY = ENTITY_TYPES.register(
        "{reg}",
        () -> EntityType.Builder.of({cls}::new, MobCategory.{cat})
            .sized({spec.hitbox_width}f, {spec.hitbox_height}f)
            .clientTrackingRange(10)
            .build(new ResourceLocation("{mod}", "{reg}"))
    );

    private {cls}Entities() {{}}

    public static void register(IEventBus bus) {{
        ENTITY_TYPES.register(bus);
    }}
}}
"""


def _attributes_java(spec: MobScaffoldSpec) -> str:
    pkg = spec.java_package
    cls = spec.entity_class_name
    mod = spec.mod_id
    return f"""package {pkg};

import net.minecraftforge.event.entity.EntityAttributeCreationEvent;
import net.minecraftforge.eventbus.api.SubscribeEvent;
import net.minecraftforge.fml.common.Mod;

@Mod.EventBusSubscriber(modid = "{mod}", bus = Mod.EventBusSubscriber.Bus.MOD)
public final class {cls}EntityAttributes {{
    private {cls}EntityAttributes() {{}}

    @SubscribeEvent
    public static void onEntityAttributeCreation(EntityAttributeCreationEvent event) {{
        event.put({cls}Entities.ENTITY.get(), {cls}.createAttributes().build());
    }}
}}
"""


def _goals_java(spec: MobScaffoldSpec) -> str:
    pkg = spec.java_package
    cls = spec.entity_class_name
    return f"""package {pkg};

import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.entity.ai.goal.Goal;
import net.minecraft.world.phys.Vec3;

import java.util.EnumSet;

final class ForagerLeapMeleeGoal extends Goal {{
    private final {cls} mob;
    private final float leapXZ;
    private final float leapY;
    private int cooldown = 0;

    ForagerLeapMeleeGoal({cls} mob, float leapXZ, float leapY) {{
        this.mob = mob;
        this.leapXZ = leapXZ;
        this.leapY = leapY;
        this.setFlags(EnumSet.of(Flag.MOVE, Flag.JUMP));
    }}

    @Override
    public boolean canUse() {{
        LivingEntity t = mob.getTarget();
        if (t == null || !t.isAlive()) return false;
        if (cooldown-- > 0) return false;
        double d = mob.distanceToSqr(t);
        return d > 6 && d < 256 && mob.onGround();
    }}

    @Override
    public void start() {{
        LivingEntity t = mob.getTarget();
        if (t == null) return;
        Vec3 dir = t.position().subtract(mob.position()).normalize();
        mob.setDeltaMovement(dir.x * leapXZ, leapY, dir.z * leapXZ);
        mob.hurtMarked = true;
        cooldown = 35;
    }}
}}

final class ForagerAoESlamGoal extends Goal {{
    private final {cls} mob;
    private final int intervalTicks;
    private final float radius;
    private final float damage;
    private int tick;

    ForagerAoESlamGoal({cls} mob, int intervalTicks, float radius, float damage) {{
        this.mob = mob;
        this.intervalTicks = Math.max(20, intervalTicks);
        this.radius = radius;
        this.damage = damage;
    }}

    @Override
    public boolean canUse() {{
        return mob.getTarget() != null && mob.getTarget().isAlive();
    }}

    @Override
    public void tick() {{
        if (++tick % intervalTicks != 0) return;
        LivingEntity t = mob.getTarget();
        if (t == null) return;
        if (mob.distanceToSqr(t) > radius * radius) return;
        if (!mob.level().isClientSide) {{
            for (LivingEntity e : mob.level().getEntitiesOfClass(LivingEntity.class, mob.getBoundingBox().inflate(radius))) {{
                if (e != mob && e.isAlive() && mob.canAttack(e)) {{
                    e.hurt(mob.damageSources().mobAttack(mob), e == t ? damage : damage * 0.65f);
                }}
            }}
        }}
    }}
}}

final class ForagerRangedPopshotGoal extends Goal {{
    private final {cls} mob;
    private final int cooldownTicks;
    private final float damage;
    private int cd = 0;

    ForagerRangedPopshotGoal({cls} mob, int cooldownTicks, float damage) {{
        this.mob = mob;
        this.cooldownTicks = Math.max(10, cooldownTicks);
        this.damage = damage;
    }}

    @Override
    public boolean canUse() {{
        LivingEntity t = mob.getTarget();
        return t != null && t.isAlive() && cd-- <= 0 && mob.distanceToSqr(t) < 12 * 12;
    }}

    @Override
    public void start() {{
        LivingEntity t = mob.getTarget();
        if (t == null) return;
        if (!mob.level().isClientSide) {{
            t.hurt(mob.damageSources().mobAttack(mob), damage);
        }}
        cd = cooldownTicks;
    }}
}}
"""


def _lang_json(spec: MobScaffoldSpec) -> str:
    key = f"entity.{spec.mod_id}.{spec.registry_name}"
    return json.dumps({key: spec.display_name}, indent=2, ensure_ascii=True)


def build_mob_scaffold_zip(spec: MobScaffoldSpec) -> bytes:
    spec = MobScaffoldSpec(**{f.name: getattr(spec, f.name) for f in fields(MobScaffoldSpec)})
    buf = io.BytesIO()
    root = "src/main/java/" + spec.java_package.replace(".", "/")
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("README_FORAGER_MOB.md", _readme(spec))
        zf.writestr("docs/GECKOLIB_NOTES.md", _gecko_notes(spec))
        zf.writestr(f"{root}/{spec.entity_class_name}.java", _entity_java(spec))
        zf.writestr(f"{root}/{spec.entity_class_name}Entities.java", _registrar_java(spec))
        zf.writestr(f"{root}/{spec.entity_class_name}EntityAttributes.java", _attributes_java(spec))
        zf.writestr(f"{root}/ForagerMobGoals.java", _goals_java(spec))
        zf.writestr(
            f"src/main/resources/assets/{spec.mod_id}/lang/en_us.json",
            _lang_json(spec),
        )
        play = load_mob_authoring_playbooks()
        if play:
            zf.writestr(
                "docs/mob_authoring_playbooks.json",
                json.dumps({"playbooks": play}, indent=2, ensure_ascii=True),
            )
    return buf.getvalue()


def mob_scaffold_spec_from_mapping(m: Mapping[str, Any]) -> MobScaffoldSpec:
    ab = m.get("abilities")
    if isinstance(ab, str):
        abilities = tuple(x.strip() for x in ab.split(",") if x.strip())
    elif isinstance(ab, (list, tuple)):
        abilities = tuple(str(x).strip() for x in ab if str(x).strip())
    else:
        abilities = ()
    return MobScaffoldSpec(
        mod_id=str(m.get("mod_id") or "forager_mobdemo"),
        java_package=str(m.get("java_package") or "com.forager.mobdemo.mobs"),
        entity_class_name=str(m.get("entity_class_name") or "AshDrake"),
        registry_name=str(m.get("registry_name") or ""),
        display_name=str(m.get("display_name") or "Ash Drake"),
        mob_category=str(m.get("mob_category") or "MONSTER"),
        hitbox_width=float(m.get("hitbox_width") or 1.6),
        hitbox_height=float(m.get("hitbox_height") or 2.2),
        max_health=float(m.get("max_health") or 40),
        movement_speed=float(m.get("movement_speed") or 0.26),
        attack_damage=float(m.get("attack_damage") or 5),
        armor=float(m.get("armor") or 2),
        summon_cap=int(m.get("summon_cap") or 3),
        abilities=abilities,
    )
