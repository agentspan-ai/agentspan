export interface SecretListItem {
  name: string;       // e.g. "GITHUB_TOKEN"
  partial: string;    // e.g. "ghp_...6789"
  updated_at: string; // ISO-8601
  tags?: { key: string; value: string }[];
}
