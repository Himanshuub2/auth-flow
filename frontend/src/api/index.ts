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

export const deleteEvent = (id: number) =>
  client.delete(`/events/${id}`);

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
