// frontend/src/lib/api.ts
const API_BASE = process.env.NEXT_PUBLIC_API_BASE;

export async function uploadInvoice(file: File, userId: string) {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("userId", userId);

  const res = await fetch(`${API_BASE}/upload_invoice/`, {
    method: "POST",
    body: formData,
  });

  if (!res.ok) {
    throw new Error(`Upload failed: ${res.statusText}`);
  }
  return await res.json();
}

export async function listInvoices(userId: string) {
  const res = await fetch(`${API_BASE}/invoices?userId=${userId}`);
  if (!res.ok) {
    throw new Error(`Fetch failed: ${res.statusText}`);
  }
  return await res.json();
}

type SyncUserParams = {
  userId: string;
  email?: string | null;
  displayName?: string | null;
  userAgent?: string; // optional
};

export async function syncUser(params: SyncUserParams) {
  const res = await fetch(`${API_BASE}/users/sync`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  if (!res.ok) throw new Error(`User sync failed: ${res.statusText}`);
  return await res.json();
}

export async function askChat(userId: string, question: string) {
  const res = await fetch(`${API_BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ userId, question }),
  });
  if (!res.ok) throw new Error(`Chat failed: ${res.statusText}`);
  return (await res.json()) as {
    answer: string;
    invoices?: any[];
    csv_base64?: string;
  };
}