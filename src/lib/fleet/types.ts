/** Shared types for the Distributed Predictive Fleet Graph frontend. */

export interface MapNode {
  id: string;
  type: 'junction' | 'bay' | 'pickup' | 'drop' | 'charge' | 'staging';
  x: number;
  y: number;
  label?: string;
  capacity: number;
  aisle?: string;
}

export interface MapEdge {
  id: string;
  type: string;
  u: string;
  v: string;
  capacity: number;
  width: number;
  speed: number;
  length: number;
}

export interface WarehouseMap {
  meta: {
    id: string;
    description: string;
    units: string;
    bounds: [number, number];
    junction_box: number;
    bay_dwell_pick_s: number;
    bay_dwell_drop_s: number;
  };
  nodes: MapNode[];
  edges: MapEdge[];
  aisles: Record<string, { edges: string[]; south: string; north: string; jec: string | null }>;
  jecs: Record<string, { junction: string; gate: string | null; covers: string[] }>;
  zones_roles: Record<string, string>;
  spawn: { rid: string; node: string; pos?: [number, number] }[];
}

export interface IntentStep {
  edge: string;
  dir: number;
  eta_in: number;
  eta_out: number;
}

export interface IntentTarget {
  resource: string;
  eta: number;
  dur: number;
}

export interface RobotView {
  robot: string;
  t: number;
  pos: [number, number];
  edge: string;
  s: number;
  dir: number;
  node: string;
  speed: number;
  battery: number;
  state: string;
  task_id: string;
  route_head: string[];
  waiting: boolean;
  wait_s: number;
  effective_priority: number;
  yields: number;
  denials: number;
  counters: Record<string, number>;
  stats: Record<string, number>;
  intent: { route: IntentStep[]; targets: IntentTarget[]; urgency: number; confidence: number } | null;
}

export interface JecView {
  jec: string;
  junction: string;
  gate: string;
  alive: boolean;
  blocked: boolean;
  occupancy: number;
  predicted: Record<string, number>;
  congestion: number;
  queue: { resource: string; robot: string; priority: number; t: number; dir?: number }[];
  reservations: {
    resv_id: string; resource: string; robot: string; start: number;
    end: number; priority: number; state: string; lease: number;
  }[];
  gate_state: { dir: number; holders: string[]; since?: number; occupants?: { robot: string; dir: number }[] };
  conflicts: ConflictCell[];
  approaching: { robot: string; eta: number }[];
  counters: Record<string, number>;
  predictor: string;
  utilization: number;
  stats: Record<string, number>;
}

export interface ConflictCell {
  cell: string;
  resource: string;
  members: string[];
  t: number;
  emitter: string;
  mode: string;
  expired?: boolean;
}

export interface DecisionEvent {
  agent: string;
  kind: string;
  t: number;
  type: string;
  goal: string;
  chosen: string[];
  candidates: { route: string[]; breakdown: Record<string, number> }[];
  greedy_route: string[];
  prosocial: boolean;
  weights: Record<string, number>;
  mode: string;
}

export interface TaskFeedItem { t: number; task_id: string; state: string; robot: string }

export interface ContextEventItem {
  t: number; type: string; value: string; reporter: string; ttl: number;
}

export interface Snapshot {
  seq?: number;
  t: number;
  robots: RobotView[];
  jecs: JecView[];
  allocator: Record<string, unknown>;
  conflicts: ConflictCell[];
  gate_claims: Record<string, unknown[]>;
  decisions: DecisionEvent[];
  task_feed: TaskFeedItem[];
  context_events: ContextEventItem[];
  supervisor: { processes?: { name: string; alive: boolean; pid: number; cpu_pct: number; rss_mb: number }[] };
}

export interface TelemetryDelta {
  seq: number;
  t: number;
  robots: Partial<RobotView & { robot: string }>[];
}

export interface LiveMetrics {
  t: number;
  robots_online: number;
  jecs_online: number;
  tasks_done: number;
  tasks_pending: number;
  tasks_active: number;
  mean_wait_s: number;
  p95_wait_s: number;
  distance_m: number;
  energy_j: number;
  vetoes: number;
  replans: number;
  collisions: number;
  messages_per_s: number;
  bytes_per_s: number;
  conflicts_active: number;
}

export interface StreamEvent {
  kind: string;
  t: number;
  robot?: string;
  [key: string]: unknown;
}

export interface ExperimentRun {
  mode: string;
  mode_label: string;
  seed: number;
  scenario: string;
  tag?: string;
  tasks_done: number;
  tasks_per_hour: number;
  tasks_failed: number;
  tasks_reassigned: number;
  mean_wait_s: number;
  p95_wait_s: number;
  max_wait_s: number;
  total_distance_m: number;
  vetoes: number;
  replans: number;
  collisions: number;
  near_misses: number;
  deadlocks: number;
  stalled_robots: number;
  reservation_grants: number;
  reservation_denials: number;
  jec_utilization: number;
  messages_per_s: number;
  bytes_per_s: number;
  conflict_cells_formed: number;
  wall_s: number;
}

export interface ResultsBundle {
  run_dir: string;
  aggregate: Record<string, Record<string, number>>;
  runs: ExperimentRun[];
}

export type Horizon = 'now' | 2 | 5 | 10;
