export interface CredentialListItem {
  name: string;       // e.g. "GITHUB_TOKEN"
  partial: string;    // e.g. "ghp_...6789"
  updated_at: string; // ISO-8601
}

export interface BindingMeta {
  logical_key: string; // e.g. "GH_TOKEN" (the alias)
  store_name: string;  // e.g. "GITHUB_TOKEN" (the stored credential name)
}

export interface LoginRequest {
  username: string;
  password: string;
}

export interface LoginResponse {
  token: string;
  user: { id: string; username: string; name: string };
}
