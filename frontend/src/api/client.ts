const API = 'http://192.168.0.204:8080';

export const getCourses = () =>
  fetch(`${API}/api/courses`).then(r => r.json());

export const getCourse = (id: string) =>
  fetch(`${API}/api/courses/${id}`).then(r => r.json());

export const getTopics = (courseId: string) =>
  fetch(`${API}/api/topics?course_id=${courseId}`).then(r => r.json());

export const getChallenge = (id: string) =>
  fetch(`${API}/api/challenges/${id}`).then(r => r.json());

export const getChallenges = (topicId: string, status?: string) =>
  fetch(`${API}/api/challenges?topic_id=${topicId}${status ? `&status=${status}` : ''}`).then(r => r.json());

export const startChallenge = (id: string): Promise<{container_id: string, ttyd_port: number}> =>
  fetch(`${API}/api/challenges/${id}/start`, { method: 'POST' }).then(r => r.json());

export const submitChallenge = (id: string, container_id: string): Promise<{passed: boolean, output: string}> =>
  fetch(`${API}/api/challenges/${id}/submit`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ container_id })
  }).then(r => r.json());

export const skipChallenge = (id: string) =>
  fetch(`${API}/api/challenges/${id}/skip`, { method: 'POST' }).then(r => r.json());

export const processFile = (file_path: string) =>
  fetch(`${API}/api/grinder/process`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ file_path })
  }).then(r => r.json());

export const getStats = () =>
  fetch(`${API}/api/progress/summary?user_id=default`).then(r => r.json());

export const getCourseProgress = (id: string) =>
  fetch(`${API}/api/progress/course/${id}`).then(r => r.json());

export const getWeakTopics = () =>
  fetch(`${API}/api/progress/weak-topics`).then(r => r.json());

export const getProgressStats = () =>
  fetch(`${API}/api/progress/stats`).then(r => r.json());

export const getActivityHeatmap = () =>
  fetch(`${API}/api/progress/activity`).then(r => r.json());

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
  return fetch(`${API}/api/grinder/upload`, {
    method: 'POST',
    body: formData
  }).then(r => r.json());
};

export const getGrinderStatus = () =>
  fetch(`${API}/api/grinder/status`).then(r => r.json());

// New async job API
export interface CreateJobResponse {
  success: boolean;
  job_id: string;
  message: string;
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

export const createImportJob = (file: File): Promise<CreateJobResponse> => {
  const formData = new FormData();
  formData.append('file', file);
  return fetch(`${API}/api/grinder/jobs`, {
    method: 'POST',
    body: formData
  }).then(r => r.json());
};

export const getJobStatus = (jobId: string): Promise<JobStatusResponse> =>
  fetch(`${API}/api/grinder/jobs/${jobId}`).then(r => r.json());

export const getJobLogs = (jobId: string): Promise<string> =>
  fetch(`${API}/api/grinder/jobs/${jobId}/logs`).then(r => r.text());

export const cancelJob = (jobId: string): Promise<{success: boolean; message: string}> =>
  fetch(`${API}/api/grinder/jobs/${jobId}`, {
    method: 'DELETE'
  }).then(r => r.json());

export const deleteCourse = (courseId: string): Promise<{success: boolean; message: string}> =>
  fetch(`${API}/api/courses/${courseId}`, {
    method: 'DELETE'
  }).then(r => r.json());
