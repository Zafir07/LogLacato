// Tipos espelhando os esquemas da API (backend/app/schemas/api.py).

export type Role = "admin" | "gestor" | "coletor" | "leitura";
export type TripStatus = "planejada" | "em_andamento" | "finalizada" | "cancelada";
export type Severity = "info" | "atencao" | "critico";
export type AlertStatus = "aberto" | "reconhecido" | "encerrado";
export type Decision = "aceito" | "recusado" | "reclassificado";

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface User {
  id: number;
  name: string;
  email: string;
  role: Role;
  active: boolean;
  created_at: string;
}

export interface Vehicle {
  id: number;
  plate: string;
  model: string;
  capacity_liters: number;
  status: "ativo" | "manutencao" | "inativo";
  is_simulated: boolean;
  device_id: string | null;
  created_at: string;
}

export interface Driver {
  id: number;
  name: string;
  document: string;
  phone: string | null;
  status: "ativo" | "inativo";
  created_at: string;
}

export interface Device {
  id: string;
  serial_number: string | null;
  vehicle_id: number | null;
  vehicle_plate: string | null;
  is_simulated: boolean;
  connection_status: "online" | "offline" | "desconhecido";
  last_seen_at: string | null;
  firmware_version: string | null;
  last_status: Record<string, unknown> | null;
}

export interface Trip {
  id: number;
  code: string;
  vehicle_id: number;
  vehicle_plate: string | null;
  driver_id: number;
  driver_name: string | null;
  device_id: string | null;
  origin: string;
  destination: string;
  volume_liters: number | null;
  departure_at: string | null;
  expected_arrival_at: string | null;
  arrival_at: string | null;
  status: TripStatus;
  is_simulated: boolean;
  notes: string | null;
  created_at: string;
  open_alerts: number;
}

export interface Sample {
  id: number;
  trip_id: number;
  trip_code: string | null;
  collected_at: string;
  producer: string;
  acidity_dornic: string | null;
  density: string | null;
  volume_liters: number | null;
  milk_temperature: string | null;
  ph_manual: string | null;
  seal_code: string | null;
  decision: Decision;
  notes: string | null;
  corrects_id: number | null;
  created_at: string;
  out_of_range: string[];
}

export interface Alert {
  id: number;
  type: string;
  parameter: string | null;
  trip_id: number | null;
  trip_code: string | null;
  device_id: string | null;
  measured_value: string | null;
  reference_min: string | null;
  reference_max: string | null;
  severity: Severity;
  status: AlertStatus;
  title: string;
  description: string;
  is_simulated: boolean;
  occurrences: number;
  first_seen_at: string;
  last_seen_at: string;
  acknowledged_at: string | null;
  closed_at: string | null;
  close_reason: string | null;
}

export interface Reading {
  id: number;
  device_id: string;
  trip_id: number | null;
  msg_id: string;
  measured_at: string | null;
  received_at: string;
  time_source: string;
  ph: string | number | null;
  ph_voltage: string | number | null;
  milk_temperature: string | number | null;
  air_temperature: string | number | null;
  air_humidity: string | number | null;
  lat: string | number | null;
  lon: string | number | null;
  sensor_flags: number;
  buffered: boolean;
  is_simulated: boolean;
  validation_status: "valid" | "partial" | "invalid" | "time_unknown";
  validation_errors: string[] | null;
}

export interface QualityParameter {
  id: number;
  parameter: "ph" | "milk_temperature" | "acidity_dornic" | "density";
  context: "coleta" | "transporte" | "recepcao";
  minimum_value: string | null;
  maximum_value: string | null;
  unit: string;
  source_reference: string;
  needs_review: boolean;
  valid_from: string;
  valid_to: string | null;
}

export interface Overview {
  volume_liters: number;
  trips: number;
  trips_finished: number;
  trips_by_status: Partial<Record<TripStatus, number>>;
  vehicles_in_operation: number;
  vehicles_total: number;
  milk_temp_avg: number | null;
  ph_avg: number | null;
  readings_valid: number;
  milk_temp_readings: number;
  acidity_avg: number | null;
  acidity_samples: number;
  alerts_active: number;
  alerts_by_severity: Partial<Record<Severity, number>>;
  devices_online: number;
  devices_total: number;
  simulated_devices: number;
}

export interface SeriesPoint {
  t: string;
  avg: number | null;
  min: number | null;
  max: number | null;
  n: number;
}

export interface Series {
  metric: string;
  bucket: "minute" | "hour" | "day";
  limits: { min: number | null; max: number | null; unit: string; source: string } | null;
  points: SeriesPoint[];
}

export interface TripComparison {
  id: number;
  code: string;
  status: TripStatus;
  is_simulated: boolean;
  vehicle_plate: string;
  driver_name: string;
  departure_at: string | null;
  volume_liters: number | null;
  ph_avg: number | null;
  milk_temp_max: number | null;
  readings: number;
  acidity_avg: number | null;
  samples_rejected: number;
  alerts: number;
  last_gps: { lat: number; lon: number } | null;
}

export interface LiveDevice {
  device_id: string;
  is_simulated: boolean;
  connection_status: "online" | "offline" | "desconhecido";
  firmware_version: string | null;
  last_status: Record<string, any> | null;
  last_seen_at: string | null;
  vehicle_plate: string | null;
  trip: { id: number; code: string } | null;
  last_reading: Reading | null;
  reading_age_s: number | null;
  is_live: boolean;
  last_sample: { acidity_dornic: string | null; collected_at: string; producer: string } | null;
}

export interface Health {
  status: "ok" | "degraded";
  checks: Record<string, { ok: boolean; error: string | null; details: Record<string, any> }>;
}
