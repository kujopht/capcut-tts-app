/** Điểm vào duy nhất của lõi mô phỏng (không DOM). Test và runtime đều import từ đây. */
export * from "./constants";
export * from "./types";
export { Rng } from "./rng";
export { TileMap, T, moveFoot, rectsOverlap, footToRect } from "./tilemap";
export { Player } from "./player";
export type { AttackKind, PlayerAnim, PlayerAbilities } from "./player";
export { Enemy, ENEMY_SPEC, resetEnemyIds, enemyOverlaps } from "./enemies";
export type { EnemyKind, EnemyState, EnemyDef } from "./enemies";
export { Boss, BossScheduler, BOSS, BOSS_ATTACKS, PHASE1_ATTACKS, PHASE2_ATTACKS } from "./boss";
export type { BossAttack, BossPhase, BossState, BossHazard, Fragment, GlyphShot } from "./boss";
export { ROOM_ORDER, rooms, room, spawnPos, describeRoom } from "./rooms";
export type { RoomDef, ExitDef, ThingDef, CycleHazard, SpawnDef } from "./rooms";
export { CAPTIONS, MEMORY_TEXT, ENDINGS, ENDING_CHOICE, memoryCaption } from "./lore";
export type { Caption, MemoryText, EndingText } from "./lore";
export { defaultSave, sanitizeSave, MemoryStore, hasProgress, endingEligibility, CHECKPOINT_IDS, SAVE_KEY, SAVE_VERSION } from "./save";
export type { SaveData, SaveSettings, SaveStore, CheckpointId } from "./save";
export { Game, checkpointSpawn, cycleState } from "./game";
export type { GameMode, GameOptions, GameResult, CycleState, EndingStage } from "./game";
