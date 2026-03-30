const API = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '');

async function getErrorMessage(response: Response): Promise<string> {
  try {
    const payload = await response.json();
    if (typeof payload?.detail === 'string') return payload.detail;
    if (typeof payload?.message === 'string') return payload.message;
  } catch {
    // fall through to plain text/HTTP status
  }

  try {
    const text = await response.text();
    if (text.trim()) return text;
  } catch {
    // ignore
  }

  return `${response.status} ${response.statusText}`;
}

async function apiFetchJson<T = any>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API}${path}`, init);
  if (!response.ok) {
    throw new Error(await getErrorMessage(response));
  }
  return response.json() as Promise<T>;
}

async function apiFetchText(path: string, init?: RequestInit): Promise<string> {
  const response = await fetch(`${API}${path}`, init);
  if (!response.ok) {
    throw new Error(await getErrorMessage(response));
  }
  return response.text();
}

export const getCourses = () =>
  apiFetchJson(`/api/courses`);

export const getCourse = (id: string) =>
  apiFetchJson(`/api/courses/${id}`);

export const getTopics = (courseId: string) =>
  apiFetchJson(`/api/courses/${courseId}/topics`);

export const getChallenge = (id: string) =>
  apiFetchJson(`/api/challenges/${id}`);

export const getChallenges = (topicId: string, status?: string) =>
  apiFetchJson(`/api/challenges?topic_id=${topicId}${status ? `&status=${status}` : ''}`);

export const startChallenge = (id: string): Promise<{container_id: string, port: number}> =>
  apiFetchJson(`/api/challenges/${id}/start`, { method: 'POST' });

export const submitChallenge = (
  id: string,
  container_id: string,
  user_id: string = 'default',
): Promise<{passed: boolean, output: string}> =>
  apiFetchJson(`/api/challenges/${id}/submit`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ container_id, user_id })
  });

export const skipChallenge = (id: string, user_id: string = 'default') =>
  apiFetchJson(`/api/challenges/${id}/skip`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_id }),
  });

export const processFile = (file_path: string) =>
  apiFetchJson(`/api/grinder/process`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ file_path })
  });

export const getStats = () =>
  apiFetchJson(`/api/progress/summary?user_id=default`);

export const getCourseProgress = (id: string) =>
  apiFetchJson(`/api/progress/course/${id}?user_id=default`);

export const getWeakTopics = () =>
  apiFetchJson(`/api/progress/weak-topics?user_id=default`);

export const getProgressStats = () =>
  apiFetchJson(`/api/progress/stats?user_id=default`);

export const getActivityHeatmap = () =>
  apiFetchJson(`/api/progress/activity?user_id=default`);

export interface UploadResult {
  success: boolean;
  message: string;
  course_id?: string;
  topics_count?: number;
  challenges_count?: number;
  status?: string;
}

export const uploadDocument = (file: File): Promise<UploadResult> => {
  const formData = new FormData();
  formData.append('file', file);
  return apiFetchJson(`/api/grinder/upload`, {
    method: 'POST',
    body: formData
  });
};

export const getGrinderStatus = () =>
  apiFetchJson(`/api/grinder/status`);

// New async job API
export interface CreateJobResponse {
  success: boolean;
  job_id?: string;
  message: string;
  legacy?: boolean;
  course_id?: string;
  topics_count?: number;
  challenges_count?: number;
  status?: string;
}

export interface JobStatusResponse {
  id: string;
  status: 'pending' | 'processing' | 'completed' | 'error';
  progress_percent: number;
  course_id: string | null;
  topics_count: number;
  challenges_count: number;
  error_message: string | null;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
}

export const createImportJob = async (file: File): Promise<CreateJobResponse> => {
  const formData = new FormData();
  formData.append('file', file);

  const jobsResponse = await fetch(`${API}/api/grinder/jobs`, {
    method: 'POST',
    body: formData
  });

  if (jobsResponse.ok) {
    const data = await jobsResponse.json() as CreateJobResponse;
    return {
      ...data,
      legacy: false,
    };
  }

  // Some running backends expose only legacy synchronous grinder endpoints.
  // Gracefully fallback so UI still works instead of hard-failing on 405/404.
  if (![404, 405, 501].includes(jobsResponse.status)) {
    throw new Error(await getErrorMessage(jobsResponse));
  }

  const legacyForm = new FormData();
  legacyForm.append('file', file);

  const legacyResponse = await fetch(`${API}/api/grinder/upload`, {
    method: 'POST',
    body: legacyForm,
  });

  if (!legacyResponse.ok) {
    throw new Error(await getErrorMessage(legacyResponse));
  }

  const legacyData = await legacyResponse.json() as UploadResult;

  if (!legacyData.success) {
    throw new Error(legacyData.message || 'Legacy upload failed');
  }

  return {
    success: true,
    message: legacyData.message || 'Processed via legacy grinder endpoint',
    legacy: true,
    course_id: legacyData.course_id,
    topics_count: legacyData.topics_count,
    challenges_count: legacyData.challenges_count,
    status: legacyData.status,
  };
};

export const getJobStatus = (jobId: string): Promise<JobStatusResponse> =>
  apiFetchJson(`/api/grinder/jobs/${jobId}`);

export const getJobLogs = (jobId: string): Promise<string> =>
  apiFetchText(`/api/grinder/jobs/${jobId}/logs`);

export const cancelJob = (jobId: string): Promise<{success: boolean; message: string}> =>
  apiFetchJson(`/api/grinder/jobs/${jobId}`, {
    method: 'DELETE'
  });

export const deleteCourse = (courseId: string): Promise<{success: boolean; message: string}> =>
  apiFetchJson(`/api/courses/${courseId}`, {
    method: 'DELETE'
  });

export interface AdminCourseChallenge {
  id: string;
  topic_id: string;
  topic_name: string;
  type: 'command' | 'output' | 'file' | string;
  difficulty: 'easy' | 'medium' | 'hard' | string;
  question: string;
  sandbox_image: string;
  validation_script: string;
  is_active: boolean;
  order: number;
  created_at?: string | null;
  quality_score?: number;
  quality_flags?: string[];
  weak_validation_reason?: string | null;
  attempts?: number;
  passes?: number;
  pass_rate?: number | null;
}

export interface AdminCourseChallengesResponse {
  course: {
    id: string;
    title: string;
    description: string;
  };
  challenges: AdminCourseChallenge[];
}

export const getAdminCourseChallenges = (
  courseId: string,
  includeInactive: boolean = true,
): Promise<AdminCourseChallengesResponse> =>
  apiFetchJson(`/api/admin/courses/${courseId}/challenges?include_inactive=${includeInactive ? 'true' : 'false'}`);

export const approveAdminChallenge = (challengeId: string): Promise<{success: boolean; challenge_id: string; is_active: boolean}> =>
  apiFetchJson(`/api/admin/challenges/${challengeId}/approve`, {
    method: 'POST',
  });

export const deleteAdminChallenge = (challengeId: string): Promise<{success: boolean; challenge_id: string; is_active: boolean}> =>
  apiFetchJson(`/api/admin/challenges/${challengeId}`, {
    method: 'DELETE',
  });

export const hideAllAdminCourseChallenges = (courseId: string): Promise<{success: boolean; course_id: string; updated: number; is_active: boolean}> =>
  apiFetchJson(`/api/admin/courses/${courseId}/challenges/hide-all`, {
    method: 'POST',
  });

export const approveAllAdminCourseChallenges = (courseId: string): Promise<{success: boolean; course_id: string; updated: number; is_active: boolean}> =>
  apiFetchJson(`/api/admin/courses/${courseId}/challenges/approve-all`, {
    method: 'POST',
  });

export const bulkSetAdminCourseChallengesActive = (
  courseId: string,
  challengeIds: string[],
  isActive: boolean,
): Promise<{
  success: boolean;
  course_id: string;
  requested: number;
  found: number;
  updated: number;
  is_active: boolean;
  missing_ids: string[];
}> =>
  apiFetchJson(`/api/admin/courses/${courseId}/challenges/bulk-set-active`, {
    method: 'POST',
    body: JSON.stringify({ challenge_ids: challengeIds, is_active: isActive }),
  });
