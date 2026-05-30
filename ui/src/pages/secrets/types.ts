export interface SecretListItem {
  name: string;       // e.g. "GITHUB_TOKEN"
  partial: string;    // e.g. "ghp_...6789"
  updated_at: string; // ISO-8601
  tags?: { key: string; value: string }[];
}

export interface LoginRequest {
  username: string;
  password: string;
}

export interface LoginResponse {
  token: string;
  user: { id: string; username: string; name: string };
}
