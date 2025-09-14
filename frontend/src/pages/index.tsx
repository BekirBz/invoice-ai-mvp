// pages/index.tsx
import { useEffect, useMemo, useState } from "react";
import Head from "next/head";
import { uploadInvoice, listInvoices, askChat } from "@/lib/api";
import { useAuth } from "@/lib/auth";

type Invoice = {
  id: string;
  userId: string;
  filename: string;
  ocr_text?: string[];
  vendor?: string | null;
  date?: string | null;
  currency?: string | null;
  amount?: number | null;
  vat?: number | null;
  fraud_score?: number | null;
  createdAt?: string | null;
  language?: string | null;
  docType?: string | null;
};

type ChatResp = {
  answer: string;
  invoices?: Invoice[];
  csv_base64?: string | null;
};

// locale-stable money formatter (avoid hydration mismatch)
const money = (v: number) =>
  new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
  }).format(v || 0);

export default function Home() {
  const { user, loading: authLoading, authBusy, signInGoogle, signInFacebook, signOutUser } = useAuth();

  const [file, setFile] = useState<File | null>(null);
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [loading, setLoading] = useState(false);
  const [listing, setListing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Invoice | null>(null);

  // KPIs
  const kpis = useMemo(() => {
    const count = invoices.length;
    const risky = invoices.filter((i) => (i.fraud_score ?? 0) >= 0.7).length;
    const total = invoices.reduce((s, i) => s + (i.amount ?? 0), 0);
    const totalVAT = invoices.reduce((s, i) => s + (i.vat ?? 0), 0);
    return { count, risky, total, totalVAT };
  }, [invoices]);

  // ---------- Dashboard aggregations ----------
  function monthKey(inv: Invoice): string {
    if (inv.date) {
      const d = inv.date;
      const m1 = d.match(/^(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})$/);
      if (m1) {
        const y = m1[3].length === 2 ? `20${m1[3]}` : m1[3];
        const mm = String(parseInt(m1[2], 10)).padStart(2, "0");
        return `${y}-${mm}`;
      }
      const m2 = d.match(/^(\d{4})[./-](\d{1,2})[./-]\d{1,2}$/);
      if (m2) {
        const y = m2[1];
        const mm = String(parseInt(m2[2], 10)).padStart(2, "0");
        return `${y}-${mm}`;
      }
    }
    if (inv.createdAt && inv.createdAt.length >= 7) {
      return inv.createdAt.slice(0, 7);
    }
    return "unknown";
  }

  const { byMonth, topVendors, flaggedCount } = useMemo(() => {
    const monthTotals: Record<string, number> = {};
    const vendorTotals: Record<string, number> = {};
    let flagged = 0;

    for (const inv of invoices) {
      const mk = monthKey(inv);
      const amt = inv.amount ?? 0;

      monthTotals[mk] = (monthTotals[mk] || 0) + amt;

      const vendor = inv.vendor || "Unknown vendor";
      vendorTotals[vendor] = (vendorTotals[vendor] || 0) + amt;

      if ((inv.fraud_score ?? 0) >= 0.7) flagged += 1;
    }

    const byMonth = Object.entries(monthTotals)
      .filter(([k]) => k !== "unknown")
      .sort((a, b) => (a[0] < b[0] ? -1 : 1)) as [string, number][];

    const topVendors = Object.entries(vendorTotals)
      .sort((a, b) => (b[1] as number) - (a[1] as number))
      .slice(0, 5) as [string, number][];

    return { byMonth, topVendors, flaggedCount: flagged };
  }, [invoices]);

  // ---------- Data I/O ----------
  async function refreshList() {
    if (!user) return;
    try {
      setListing(true);
      setError(null);
      const data = await listInvoices(user.uid);
      setInvoices(data);
    } catch (e: any) {
      setError(e?.message || "Failed to load invoices");
    } finally {
      setListing(false);
    }
  }

  useEffect(() => {
    if (user) refreshList();
    else setInvoices([]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user]);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!file || !user || loading) return;
    try {
      setLoading(true);
      setError(null);
      await uploadInvoice(file, user.uid);
      setFile(null);
      await refreshList();
    } catch (e: any) {
      setError(e?.message || "Upload failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <Head><title>Invoice AI MVP</title></Head>
      <div className="min-h-screen bg-neutral-950 text-neutral-100">
        <div className="mx-auto max-w-5xl px-4 py-10">
          <div className="mb-3 flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-semibold">Invoice AI – MVP</h1>
              <p className="text-neutral-400">Upload → OCR → Extract → Score → List</p>
            </div>

            {/* Auth actions */}
            <div>
              {authLoading ? (
                <span className="text-sm text-neutral-400">Loading…</span>
              ) : user ? (
                <div className="flex items-center gap-3">
                  <span className="text-sm text-neutral-300">Signed in as {user.email ?? user.uid}</span>
                  <button onClick={signOutUser} className="rounded-md bg-white/10 px-3 py-1 text-sm hover:bg-white/20">
                    Sign out
                  </button>
                </div>
              ) : (
                <div className="flex gap-3">
                  <button
                    onClick={signInGoogle}
                    disabled={authBusy}
                    className="rounded-md bg-white/10 px-3 py-2 text-sm hover:bg-white/20 disabled:opacity-60"
                  >
                    {authBusy ? "Signing in…" : "Sign in with Google"}
                  </button>
                  <button
                    onClick={signInFacebook}
                    disabled={authBusy}
                    className="rounded-md bg-blue-600 px-3 py-2 text-sm hover:bg-blue-700 disabled:opacity-60"
                  >
                    {authBusy ? "Opening Facebook…" : "Sign in with Facebook"}
                  </button>
                </div>
              )}
            </div>
          </div>

          {/* If not signed in */}
          {!authLoading && !user && (
            <div className="mt-10 rounded-xl border border-neutral-800 bg-neutral-900/40 p-8 text-center">
              <p className="text-neutral-300">Please sign in to upload and view your invoices.</p>
            </div>
          )}

          {/* Signed-in UI */}
          {user && (
            <>
              {/* KPIs */}
              <div className="mt-6 grid grid-cols-2 gap-4 md:grid-cols-4">
                <KPI title="Invoices" value={String(kpis.count)} />
                <KPI title="Risky" value={String(kpis.risky)} />
                <KPI title="Total" value={money(kpis.total)} />
                <KPI title="VAT" value={money(kpis.totalVAT)} />
              </div>

              {/* Upload form */}
              <form onSubmit={onSubmit} className="mt-8 rounded-xl border border-neutral-800 p-4">
                <div className="flex flex-col gap-3 md:flex-row md:items-center">
                  <input
                    type="file"
                    accept="application/pdf,image/*"
                    onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                    className="block w-full rounded-lg border border-neutral-700 bg-neutral-900 p-2 text-sm file:mr-4 file:rounded-md file:border-0 file:bg-neutral-800 file:px-3 file:py-2 file:text-neutral-200"
                  />
                  <button
                    type="submit"
                    disabled={!file || loading}
                    className="rounded-md bg-white/10 px-4 py-2 text-sm hover:bg-white/20 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {loading ? "Uploading..." : "Upload"}
                  </button>
                  <button
                    type="button"
                    onClick={refreshList}
                    disabled={listing}
                    className="rounded-md bg-white/5 px-4 py-2 text-sm hover:bg-white/15 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {listing ? "Refreshing..." : "Refresh"}
                  </button>
                </div>
                {file && (
                  <p className="mt-2 text-xs text-neutral-400">
                    Selected: <span className="text-neutral-200">{file.name}</span>
                  </p>
                )}
                {error && <p className="mt-3 text-sm text-red-400">{error}</p>}
              </form>

              {/* ----- Dashboard section ----- */}
              <div className="mt-8 grid gap-4 md:grid-cols-3">
                <div className="rounded-xl border border-neutral-800 bg-neutral-900/40 p-4 md:col-span-2">
                  <div className="mb-1 flex items-center justify-between">
                    <div className="text-xs uppercase tracking-wide text-neutral-400">Monthly totals</div>
                    <div className="text-xs text-neutral-400">
                      {byMonth.length ? `${byMonth[0][0]} → ${byMonth[byMonth.length - 1][0]}` : "No data"}
                    </div>
                  </div>
                  <MiniBarChart data={byMonth} />
                </div>

                <div className="rounded-xl border border-neutral-800 bg-neutral-900/40 p-4">
                  <div className="text-xs uppercase tracking-wide text-neutral-400">Quality</div>
                  <div className="mt-2 space-y-2 text-sm">
                    <RowStat label="Flagged (≥70%)" value={String(flaggedCount)} />
                    <RowStat label="Invoices" value={String(kpis.count)} />
                    <RowStat label="Total amount" value={money(kpis.total)} />
                    <RowStat label="Total VAT" value={money(kpis.totalVAT)} />
                  </div>
                </div>
              </div>

              <div className="mt-4 grid gap-4 md:grid-cols-3">
                <div className="rounded-xl border border-neutral-800 bg-neutral-900/40 p-4">
                  <div className="text-xs uppercase tracking-wide text-neutral-400">Top vendors</div>
                  <div className="mt-2 space-y-2 text-sm">
                    {topVendors.length === 0 && <div className="text-neutral-400">No data</div>}
                    {topVendors.map(([name, tot]) => (
                      <div key={name} className="flex items-center justify-between">
                        <span className="truncate pr-3">{name}</span>
                        <span className="font-semibold">{money(tot)}</span>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="rounded-xl border border-neutral-800 bg-neutral-900/40 p-4 md:col-span-2">
                  <div className="text-xs uppercase tracking-wide text-neutral-400">Notes</div>
                  <p className="mt-2 text-sm text-neutral-300">
                    Use the chat box (below) to ask: <em>“What invoices are risky this month”</em>,{" "}
                    <em>“Total spent in August”</em>, or <em>“Export my tax summary”</em>.
                  </p>
                </div>
              </div>

              {/* Table */}
              <div className="mt-8 overflow-x-auto rounded-xl border border-neutral-800">
                <table className="w-full text-left text-sm">
                  <thead className="bg-neutral-900/70">
                    <tr>
                      <Th>File</Th>
                      <Th>Vendor</Th>
                      <Th>Date</Th>
                      <Th>Currency</Th>
                      <Th className="text-right">Amount</Th>
                      <Th className="text-right">VAT</Th>
                      <Th className="text-right">Fraud</Th>
                      <Th>Language</Th>
                      <Th>Type</Th>
                      <Th>&nbsp;</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {invoices.length === 0 && (
                      <tr>
                        <td colSpan={10} className="px-4 py-6 text-center text-neutral-400">
                          No invoices yet. Upload a PDF or image.
                        </td>
                      </tr>
                    )}
                    {invoices.map((inv) => (
                      <tr key={inv.id} className="border-t border-neutral-900/60 hover:bg-neutral-900/40">
                        <Td>{inv.filename}</Td>
                        <Td>{inv.vendor ?? "-"}</Td>
                        <Td>{inv.date ?? "-"}</Td>
                        <Td>{inv.currency ?? "-"}</Td>
                        <Td className="text-right">{inv.amount != null ? money(inv.amount) : "-"}</Td>
                        <Td className="text-right">{inv.vat != null ? money(inv.vat) : "-"}</Td>
                        <Td className="text-right">
                          {inv.fraud_score != null ? `${(inv.fraud_score * 100).toFixed(0)}%` : "-"}
                        </Td>
                        <Td>{inv.language ?? "-"}</Td>
                        <Td>{inv.docType ?? "-"}</Td>
                        <Td className="text-right">
                          <button
                            onClick={() => setSelected(inv)}
                            className="rounded-md bg-white/10 px-3 py-1 text-xs hover:bg-white/20"
                          >
                            View OCR
                          </button>
                        </Td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Chatbot */}
              <div className="mt-6">
                <ChatBox userId={user.uid} />
              </div>

              {/* Drawer */}
              {selected && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={() => setSelected(null)}>
                  <div
                    className="max-h-[80vh] w-full max-w-3xl overflow-auto rounded-xl border border-neutral-800 bg-neutral-950 p-5"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <div className="mb-4 flex items-center justify-between">
                      <h3 className="text-lg font-semibold">{selected.filename}</h3>
                      <button onClick={() => setSelected(null)} className="rounded-md bg-white/10 px-3 py-1 text-sm hover:bg-white/20">
                        Close
                      </button>
                    </div>
                    <div className="space-y-2 text-sm">
                      {(selected.ocr_text ?? ["No OCR text"]).map((t, i) => (
                        <pre key={i} className="whitespace-pre-wrap rounded-md bg-neutral-900 p-3">
                          {t}
                        </pre>
                      ))}
                    </div>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </>
  );
}

function KPI({ title, value }: { title: string; value: string }) {
  return (
    <div className="rounded-xl border border-neutral-800 bg-neutral-900/40 p-4">
      <div className="text-xs uppercase tracking-wide text-neutral-400">{title}</div>
      <div className="mt-1 text-2xl font-semibold">{value}</div>
    </div>
  );
}
function RowStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-neutral-300">{label}</span>
      <span className="font-semibold">{value}</span>
    </div>
  );
}
function Th({ children, className = "" }: { children: any; className?: string }) {
  return <th className={`px-4 py-3 text-xs uppercase tracking-wide text-neutral-400 ${className}`}>{children}</th>;
}
function Td({ children, className = "" }: { children: any; className?: string }) {
  return <td className={`px-4 py-3 ${className}`}>{children}</td>;
}

/* ---------- Chat component ---------- */
function ChatBox({ userId }: { userId: string }) {
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [resp, setResp] = useState<ChatResp | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function ask(e: React.FormEvent) {
    e.preventDefault();
    if (!q || busy) return;
    try {
      setBusy(true);
      setErr(null);
      const r = await askChat(userId, q);
      setResp(r);
    } catch (e: any) {
      setErr(e?.message || "Chat request failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rounded-xl border border-neutral-800 bg-neutral-900/40 p-4">
      <div className="mb-2 text-sm text-neutral-300">
        Try: <code className="text-neutral-100">What invoices are risky this month</code>,{" "}
        <code className="text-neutral-100">Total spent in August</code>,{" "}
        <code className="text-neutral-100">Export my tax summary</code>
      </div>
      <form onSubmit={ask} className="flex gap-2">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Ask about your invoices…"
          className="flex-1 rounded-lg border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm"
        />
        <button
          type="submit"
          disabled={!q || busy}
          className="rounded-md bg-white/10 px-4 py-2 text-sm hover:bg-white/20 disabled:opacity-50"
        >
          {busy ? "Thinking…" : "Ask"}
        </button>
      </form>

      {err && <p className="mt-3 text-sm text-red-400">{err}</p>}

      {resp && (
        <div className="mt-4 space-y-3">
          <div className="rounded-md bg-neutral-900 p-3 text-sm">{resp.answer}</div>

          {resp.csv_base64 && (
            <a
              href={`data:text/csv;base64,${resp.csv_base64}`}
              download="tax_summary.csv"
              className="inline-block rounded-md bg-white/10 px-3 py-2 text-sm hover:bg-white/20"
            >
              Download CSV
            </a>
          )}

          {resp.invoices && resp.invoices.length > 0 && (
            <div className="overflow-x-auto rounded-md border border-neutral-800">
              <table className="w-full text-left text-xs">
                <thead className="bg-neutral-900/70">
                  <tr>
                    <Th>File</Th>
                    <Th>Vendor</Th>
                    <Th>Date</Th>
                    <Th>Currency</Th>
                    <Th className="text-right">Amount</Th>
                    <Th className="text-right">VAT</Th>
                    <Th className="text-right">Fraud</Th>
                  </tr>
                </thead>
                <tbody>
                  {resp.invoices.map((inv) => (
                    <tr key={inv.id} className="border-t border-neutral-900/60">
                      <Td>{inv.filename}</Td>
                      <Td>{inv.vendor ?? "-"}</Td>
                      <Td>{inv.date ?? "-"}</Td>
                      <Td>{inv.currency ?? "-"}</Td>
                      <Td className="text-right">{inv.amount != null ? money(inv.amount) : "-"}</Td>
                      <Td className="text-right">{inv.vat != null ? money(inv.vat) : "-"}</Td>
                      <Td className="text-right">
                        {inv.fraud_score != null ? `${(inv.fraud_score * 100).toFixed(0)}%` : "-"}
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* ---------- Tiny SVG bar chart (no deps) ---------- */
function MiniBarChart({ data }: { data: [string, number][] }) {
  const width = 420,
    height = 120,
    pad = 20;
  const max = Math.max(1, ...data.map(([, v]) => v));
  const barW = (width - pad * 2) / Math.max(1, data.length);

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="w-full">
      <line x1={pad} y1={height - pad} x2={width - pad} y2={height - pad} stroke="currentColor" opacity={0.2} />
      {data.map(([k, v], i) => {
        const x = pad + i * barW;
        const h = Math.round((v / max) * (height - pad * 2));
        const y = height - pad - h;
        return (
          <g key={k}>
            <rect x={x + 2} y={y} width={barW - 6} height={h} fill="currentColor" opacity={0.6} />
            <text x={x + barW / 2} y={height - 6} fontSize="9" textAnchor="middle" fill="currentColor" opacity={0.6}>
              {k.slice(5, 7)}
            </text>
          </g>
        );
      })}
    </svg>
  );
}