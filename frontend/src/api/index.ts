import client from "./client";
import type {
  TokenResponse,
  EventData,
  EventListResponse,
  SaveEventPayload,
  RevisionSummary,
  RevisionDetail,
  MediaItem,
  Division,
  Designation,
  DocumentData,
  DocumentListResponse,
  SaveDocumentPayload,
  DocumentTypeOption,
  LegislationOption,
  SubLegislationOption,
  LinkedOption,
  CombinedListResponse,
} from "../types";

// ---- Auth ----
export const login = (email: string, password: string) =>
  client.post<TokenResponse>("/auth/login", { email, password });

export const register = (email: string, password: string, full_name: string) =>
  client.post<TokenResponse>("/auth/register", { email, password, full_name });

// ---- Events ----

function buildFormData(payload: SaveEventPayload, files?: File[]): FormData {
  const fd = new FormData();
  fd.append("data", JSON.stringify(payload));
  if (files?.length) {
    files.forEach((f) => fd.append("files", f));
  }
  return fd;
}

export const createEvent = (payload: SaveEventPayload, files?: File[]) =>
  client.post<EventData>("/events/", buildFormData(payload, files), {
    headers: { "Content-Type": "multipart/form-data" },
  });

export const updateEvent = (id: number, payload: SaveEventPayload, files?: File[]) =>
  client.put<EventData>(`/events/${id}`, buildFormData(payload, files), {
    headers: { "Content-Type": "multipart/form-data" },
  });

export const listEvents = (page = 1, pageSize = 20, status?: string) =>
  client.get<EventListResponse>("/events/", { params: { page, page_size: pageSize, status } });

export const getEvent = (id: number) =>
  client.get<EventData>(`/events/${id}`);

export const createDraftFromEvent = (id: number) =>
  client.post<EventData>(`/events/${id}/draft`);

export const deleteEvent = (id: number, deactivate_remarks: string) =>
  client.delete(`/events/${id}`, { data: { deactivate_remarks } });

export const toggleEventStatus = (id: number) =>
  client.patch<EventData>(`/events/${id}/toggle-status`);

// ---- Media (read-only) ----
export const getMedia = (eventId: number, version?: number) =>
  client.get<MediaItem[]>(`/events/${eventId}/media/`, { params: version ? { version } : {} });

// ---- Revisions ----
export const listRevisions = (eventId: number) =>
  client.get<RevisionSummary[]>(`/events/${eventId}/revisions/`);

export const getRevisionSnapshot = (eventId: number, mediaVersion: number, revisionNumber: number) =>
  client.get<RevisionDetail>(`/events/${eventId}/revisions/${mediaVersion}/${revisionNumber}`);

// ---- Reference ----
export const getDivisions = () => client.get<Division[]>("/reference/divisions");
export const getDesignations = () => client.get<Designation[]>("/reference/designations");

// ---- Documents ----

function buildDocFormData(payload: SaveDocumentPayload, files?: File[]): FormData {
  const fd = new FormData();
  fd.append("data", JSON.stringify(payload));
  if (files?.length) {
    files.forEach((f) => fd.append("files", f));
  }
  return fd;
}

export const createDocument = (payload: SaveDocumentPayload, files?: File[]) =>
  client.post<DocumentData>("/documents/", buildDocFormData(payload, files), {
    headers: { "Content-Type": "multipart/form-data" },
  });

export const updateDocument = (id: number, payload: SaveDocumentPayload, files?: File[]) =>
  client.put<DocumentData>(`/documents/${id}`, buildDocFormData(payload, files), {
    headers: { "Content-Type": "multipart/form-data" },
  });

export const listDocuments = (page = 1, pageSize = 20, status?: string, documentType?: string) =>
  client.get<DocumentListResponse>("/documents/", {
    params: { page, page_size: pageSize, status, document_type: documentType },
  });

export const getDocument = (id: number) =>
  client.get<DocumentData>(`/documents/${id}`);

export const createDraftFromDocument = (id: number) =>
  client.post<DocumentData>(`/documents/${id}/draft`);

export const deactivateDocument = (id: number, deactivate_remarks: string) =>
  client.delete(`/documents/${id}`, { data: { deactivate_remarks } });

export const toggleDocumentStatus = (id: number) =>
  client.patch<DocumentData>(`/documents/${id}/toggle-status`);

export const getLinkedOptions = (documentType: string, excludeId?: number) =>
  client.get<LinkedOption[]>("/documents/linked-options", {
    params: { document_type: documentType, exclude_id: excludeId },
  });

// ---- Document Reference ----
export const getDocumentTypes = () =>
  client.get<DocumentTypeOption[]>("/reference/documents/document-types");

export const getLegislation = () =>
  client.get<LegislationOption[]>("/reference/documents/legislation");

export const getSubLegislation = (legislationId: number) =>
  client.get<SubLegislationOption[]>("/reference/documents/sub-legislation", {
    params: { legislation_id: legislationId },
  });

// ---- Items (generic: list, detail, revisions – events and documents) ----
export const listCombinedItems = (page = 1, pageSize = 20, itemType?: string) =>
  client.get<CombinedListResponse>("/items/", {
    params: { page, page_size: pageSize, item_type: itemType },
  });

export const getItemDetail = (itemId: number, itemType: "event" | "document") =>
  client.get<EventData | DocumentData>("/items/" + itemId, {
    params: { item_type: itemType },
  });

export const listItemRevisions = (itemId: number, itemType: "event" | "document") =>
  client.get<RevisionSummary[]>("/items/" + itemId + "/revisions", {
    params: { item_type: itemType },
  });

export const getItemRevisionSnapshot = (
  itemId: number,
  mediaVersion: number,
  revisionNumber: number,
  itemType: "event" | "document"
) =>
  client.get<RevisionDetail>("/items/" + itemId + "/revisions/" + mediaVersion + "/" + revisionNumber, {
    params: { item_type: itemType },
  });
