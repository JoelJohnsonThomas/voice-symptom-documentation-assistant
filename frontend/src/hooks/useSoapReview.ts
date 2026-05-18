import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useApiClient } from "./useApiClient";
import type {
  Annotation,
  AnnotationCreatePayload,
  AnnotationStatus,
  ApprovalResponse,
  SOAPReviewSection,
  VersionCreatePayload,
  VersionDetail,
  VersionSummary,
} from "../types/soapReview";

export function useVersionList(sessionId: string | undefined) {
  const api = useApiClient();
  return useQuery<VersionSummary[]>({
    queryKey: ["soap-versions", sessionId],
    enabled: Boolean(sessionId),
    queryFn: () => api.get<VersionSummary[]>(`/sessions/${sessionId}/versions`),
  });
}

export function useVersionDetail(sessionId: string | undefined, versionId: string | undefined) {
  const api = useApiClient();
  return useQuery<VersionDetail>({
    queryKey: ["soap-version", sessionId, versionId],
    enabled: Boolean(sessionId && versionId),
    queryFn: () => api.get<VersionDetail>(`/sessions/${sessionId}/versions/${versionId}`),
  });
}

export function useCreateVersion(sessionId: string | undefined) {
  const api = useApiClient();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: VersionCreatePayload) =>
      api.post<VersionDetail>(`/sessions/${sessionId}/versions`, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["soap-versions", sessionId] });
    },
  });
}

export function useApproveVersion(sessionId: string | undefined) {
  const api = useApiClient();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (versionId: string) =>
      api.post<ApprovalResponse>(`/sessions/${sessionId}/versions/${versionId}/approve`, {}),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["soap-annotations", sessionId] });
      qc.invalidateQueries({ queryKey: ["soap-versions", sessionId] });
    },
  });
}

interface AnnotationFilters {
  soap_section?: SOAPReviewSection;
  annotation_status?: AnnotationStatus;
}

export function useAnnotationList(sessionId: string | undefined, filters: AnnotationFilters = {}) {
  const api = useApiClient();
  const search = new URLSearchParams();
  if (filters.soap_section) search.set("soap_section", filters.soap_section);
  if (filters.annotation_status) search.set("annotation_status", filters.annotation_status);
  const query = search.toString();
  return useQuery<Annotation[]>({
    queryKey: ["soap-annotations", sessionId, filters],
    enabled: Boolean(sessionId),
    queryFn: () =>
      api.get<Annotation[]>(
        `/sessions/${sessionId}/annotations${query ? `?${query}` : ""}`,
      ),
  });
}

export function useCreateAnnotation(sessionId: string | undefined) {
  const api = useApiClient();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: AnnotationCreatePayload) =>
      api.post<Annotation>(`/sessions/${sessionId}/annotations`, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["soap-annotations", sessionId] });
    },
  });
}

export function useUpdateAnnotationStatus(sessionId: string | undefined) {
  const api = useApiClient();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, status }: { id: string; status: AnnotationStatus }) =>
      api.patch<Annotation>(`/annotations/${id}`, { status }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["soap-annotations", sessionId] });
    },
  });
}
