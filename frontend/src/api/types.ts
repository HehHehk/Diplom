export type Role = "user" | "owner" | "admin";
export type BillingUnit = "hour" | "day";

export interface User {
  id: number;
  email: string;
  full_name: string;
  role: Role;
  is_active: boolean;
  timezone: string;
  timezone_source: string;
  created_at: string;
}

export interface Equipment {
  id: number;
  owner_id: number | null;
  title: string;
  description: string;
  category: string;
  brand: string;
  price_per_hour: string | null;
  price_per_day: string | null;
  min_hours: number;
  min_days: number;
  max_hours: number;
  max_days: number;
  quantity: number;
  buffer_minutes: number;
  lead_time_minutes: number;
  working_hours: Record<string, string[][]> | null;
  timezone: string;
  specs: Record<string, unknown>;
  image_url: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
  pages: number;
}

export interface Booking {
  id: number;
  user_id: number;
  equipment_id: number;
  start_at: string;
  end_at: string;
  picked_up_at: string | null;
  returned_at: string | null;
  quantity: number;
  billing_unit: BillingUnit;
  unit_price: string;
  total_price: string;
  status: "confirmed" | "completed" | "cancelled" | "terminated" | "no_show";
  cancelled_at: string | null;
  cancelled_by: "user" | "owner" | "admin" | "system" | null;
  cancellation_reason: string | null;
  penalty_amount: string;
  refund_amount: string;
  compensation_amount: string;
  damage_amount: string;
  dispute_status: "none" | "pending" | "resolved";
  no_show_deadline: string | null;
  no_show_at: string | null;
  created_at: string;
  equipment: {
    id: number;
    title: string;
    category: string;
    brand: string;
    image_url: string;
    price_per_hour: string | null;
    price_per_day: string | null;
    timezone: string;
    owner_id: number | null;
  };
}

export interface PriceOption {
  billing_unit: BillingUnit;
  unit_price: string | null;
  units: number | null;
  total: string | null;
  available: boolean;
  problems: string[];
}

export interface BookingPreview {
  equipment_id: number;
  quantity: number;
  options: PriceOption[];
  recommended: BillingUnit | null;
}

export interface RecommendationList {
  strategy: "content" | "popular";
  items: (Equipment & { score: number })[];
}

export interface Forecast {
  equipment_id: number;
  title: string;
  period_days: number;
  total_bookings: number;
  by_weekday: { weekday: number; label: string; count: number; share: number }[];
  by_hour: { hour: number; count: number; share: number }[];
  best_weekday: string | null;
  best_hours: number[];
  recommendation: string;
}

export interface Availability {
  equipment_id: number;
  quantity: number;
  timezone: string;
  buffer_minutes: number;
  from_at: string;
  to_at: string;
  busy: { start_at: string; end_at: string; quantity: number }[];
}

export interface Dispute {
  booking_id: number;
  equipment_id: number;
  equipment_title: string;
  client_email: string;
  owner_email: string | null;
  status: "pending" | "resolved";
  reason: string | null;
  description: string | null;
  premoderated: boolean;
  created_at: string | null;
  resolved_at: string | null;
  outcome: string | null;
  total_price: string;
  penalty_amount: string;
  refund_amount: string;
  compensation_amount: string;
  damage_amount: string;
}

export interface AdminUser extends User {
  penalties_count: number;
  cancellations_count: number;
  incidents_count: number;
  damage_count: number;
  disputes_open: number;
  disputes_total_30d: number;
  disputes_rejected_30d: number;
  moderation_mode: string;
  is_abuser: boolean;
}

export interface OwnerStats {
  equipment_total: number;
  equipment_active: number;
  bookings_total: number;
  bookings_active: number;
  bookings_completed: number;
  bookings_cancelled: number;
  revenue: string;
  refunds: string;
  disputes_pending: number;
  incidents: number;
}
