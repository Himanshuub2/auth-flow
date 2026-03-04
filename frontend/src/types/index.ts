export type EventStatus = "DRAFT" | "PUBLISHED" | "ACTIVE" | "INACTIVE";
export type ApplicabilityType = "ALL" | "DIVISION" | "EMPLOYEE";
export type FileType = "IMAGE" | "VIDEO";

export interface User {
  id: number;
  email: string;
  full_name: string;
  division_cluster: string | null;
  designation: string | null;
  policy_hub_admin: boolean;
  is_admin: boolean;
  knowledge_hub_admin: boolean;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export interface MediaFileSummary {
  id: number;
  original_filename: string;
  file_type: FileType;
  file_url: string;
  media_versions: number[];
}

export interface Revision {
  id: number;
  event_id: number;
  media_version: number;
  revision_number: number;
  version_display: string;
  event_name: string;
  sub_event_name: string | null;
  event_dates: string[] | Record<string, string> | null;
  description: string | null;
  tags: string[] | null;
  created_by: number;
  created_by_name: string;
  created_at: string;
}

export interface EventData {
  id: number;
  event_name: string;
  sub_event_name: string | null;
  event_dates: string[] | Record<string, string> | null;
  description: string | null;
  tags: string[] | null;
  current_media_version: number;
  current_revision_number: number;
  version_display: string;
  status: EventStatus;
  applicability_type: ApplicabilityType;
  applicability_refs: Record<string, number[]> | null;
  draft_parent_id: number | null;
  created_by: number;
  created_by_name: string;
  created_at: string;
  updated_at: string;
  files: MediaFileSummary[];
}

export interface EventListResponse {
  items: EventData[];
  total: number;
  page: number;
  page_size: number;
}

export interface MediaItem {
  id: number;
  event_id: number;
  media_versions: number[];
  file_type: FileType;
  file_url: string;
  thumbnail_url: string | null;
  caption: string | null;
  description: string | null;
  sort_order: number;
  file_size_bytes: number;
  original_filename: string;
  created_at: string;
}

export interface RevisionDetail {
  revision: Revision;
  media_items: MediaItem[];
}

export interface Division {
  id: number;
  name: string;
}

export interface Designation {
  id: number;
  name: string;
}

export interface SaveEventPayload {
  event_name: string;
  sub_event_name?: string | null;
  event_dates?: string[] | null;
  description?: string | null;
  tags?: string[] | null;
  applicability_type: string;
  applicability_refs?: Record<string, number[]> | null;
  status: string;
  selected_filenames?: string[];
}

export interface WizardFormState {
  event_name: string;
  sub_event_name: string;
  event_dates: string[];
  description: string;
  tags: string[];
  applicability_type: ApplicabilityType;
  applicability_refs: Record<string, number[]>;
  files: File[];
  existingMedia: MediaItem[];
}
