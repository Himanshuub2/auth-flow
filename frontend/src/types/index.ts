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
  thumbnail_url: string | null;
  caption: string | null;
  description: string | null;
  media_versions: number[];
}

export interface FileMetadataItem {
  original_filename: string;
  caption: string | null;
  description: string | null;
  thumbnail_original_filename: string | null;
}

export interface RevisionSummary {
  id: number;
  media_version: number;
  revision_number: number;
  version_display: string;
  created_at: string;
  change_remarks?: string | null;
  event_id?: number;
  document_id?: number;
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
  change_remarks: string | null;
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
  replaces_document_id: number | null;
  created_by: number;
  created_by_name: string;
  created_at: string;
  updated_at: string;
  change_remarks: string | null;
  deactivate_remarks: string | null;
  deactivated_at: string | null;
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

/** Event revision snapshot */
export interface EventRevisionDetail {
  revision: Revision;
  media_items: MediaItem[];
}

/** Document revision snapshot */
export interface DocumentRevisionDetail {
  revision: DocumentRevision;
  files: DocumentFileSummary[];
}

export interface DocumentRevision {
  id: number;
  document_id: number;
  media_version: number;
  revision_number: number;
  version_display: string;
  name: string;
  document_type: DocumentType;
  tags: string[] | null;
  summary: string | null;
  applicability_type: ApplicabilityType;
  applicability_refs: Record<string, number[]> | null;
  created_by: number;
  created_by_name: string;
  created_at: string;
}

/** Union: event returns media_items, document returns files */
export type RevisionDetail = EventRevisionDetail | DocumentRevisionDetail;

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
  file_metadata?: FileMetadataItem[];
  change_remarks?: string | null;
}

export interface FileMetadataState {
  caption: string;
  description: string;
  thumbnailFile: File | null;
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
  fileMetadata: Record<string, FileMetadataState>;
  existingMedia: MediaItem[];
  change_remarks: string;
}

// ── Documents ────────────────────────────────────────────────────────────

export type DocumentType =
  | "POLICY"
  | "GUIDANCE_NOTE"
  | "LAW_REGULATION"
  | "TRAINING_MATERIAL"
  | "EWS"
  | "FAQ"
  | "LATEST_NEWS"
  | "ANNOUNCEMENTS";

export type DocumentFileType = "IMAGE" | "DOCUMENT";

export interface DocumentTypeOption {
  value: string;
  label: string;
}

export interface LegislationOption {
  id: number;
  name: string;
}

export interface SubLegislationOption {
  id: number;
  legislation_id: number;
  name: string;
}

export interface LinkedOption {
  id: number;
  name: string;
}

export interface LinkedDocumentDetail {
  id: number;
  name: string;
  document_type: string;
}

export interface DocumentFileSummary {
  id: number;
  original_filename: string;
  file_type: DocumentFileType;
  file_url: string;
  media_versions: number[];
  file_size_bytes: number;
}

export interface DocumentData {
  id: number;
  name: string;
  document_type: DocumentType;
  tags: string[] | null;
  summary: string | null;
  legislation_id: number | null;
  sub_legislation_id: number | null;
  version: number;
  next_review_date: string | null;
  download_allowed: boolean;
  linked_document_ids: number[] | null;
  applicability_type: ApplicabilityType;
  applicability_refs: Record<string, number[]> | null;
  status: EventStatus;
  current_media_version: number;
  current_revision_number: number;
  version_display: string;
  change_remarks: string | null;
  deactivate_remarks: string | null;
  deactivated_at: string | null;
  replaces_document_id: number | null;
  created_by: number;
  created_by_name: string;
  created_at: string;
  updated_at: string;
  files: DocumentFileSummary[];
  linked_document_details?: LinkedDocumentDetail[] | null;
}

export interface DocumentListResponse {
  data?: DocumentData[];
  total: number;
  page: number;
  page_size: number;
}

export interface SaveDocumentPayload {
  name: string;
  document_type: DocumentType;
  tags: string[];
  summary?: string | null;
  legislation_id?: number | null;
  sub_legislation_id?: number | null;
  version?: number;
  next_review_date?: string | null;
  download_allowed?: boolean;
  linked_document_ids?: number[] | null;
  applicability_type: string;
  applicability_refs?: Record<string, number[]> | null;
  status: string;
  selected_filenames?: string[];
  change_remarks?: string | null;
}

export interface CombinedItem {
  id: number;
  item_type: "event" | "document";
  name: string;
  document_type: string | null;
  version_display: string;
  status: string;
  created_by: number;
  created_by_name: string;
  created_at: string;
  updated_at: string;
}

export interface CombinedListResponse {
  items: CombinedItem[];
  total: number;
  page: number;
  page_size: number;
}
