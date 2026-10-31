'use client';

import { useEffect, useState } from 'react';

type Doc = { document_id: string; filename: string; status: string; page_count: number; chunk_count: number };
type Citation = { filename: string; page_number: number | null; chunk_id: string };

async function readApiResponse(response: Response): Promise<Record<string, any>> {
  const text = await response.text();
  if (!text.trim()) {
    return { detail: `The backend returned an empty response (HTTP ${response.status}). Check its deployment logs; the request may have timed out.` };
  }
  try {
    const data = JSON.parse(text);
    return data && typeof data === 'object' ? data : { detail: text };
  } catch {
    return { detail: `Backend returned a non-JSON response (HTTP ${response.status}): ${text.slice(0, 500)}` };
  }
}

export default function SearchUploadPanel() {
  const [open, setOpen] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [docs, setDocs] = useState<Doc[]>([]);
  const [selected, setSelected] = useState('');
  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState('');
  const [citations, setCitations] = useState<Citation[]>([]);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState('');
  const [error, setError] = useState('');

  async function loadDocs() {
    const response = await fetch('/api/v1/documents', { cache: 'no-store' });
    if (!response.ok) throw new Error(`Could not load documents (HTTP ${response.status}).`);
    setDocs(await response.json());
  }

  useEffect(() => { if (open) loadDocs().catch(e => setError(e.message)); }, [open]);

  async function upload() {
    if (!file) return;
    setBusy(true); setError(''); setStatus('Uploading and processing PDF…'); setAnswer('');
    try {
      const form = new FormData(); form.append('file', file);
      const response = await fetch('/api/v1/documents/upload', { method: 'POST', body: form });
      const data = await readApiResponse(response);
      if (!response.ok) throw new Error(data.detail || 'Upload failed.');
      setSelected(data.document_id); setFile(null);
      setStatus(`Uploaded ${data.filename}: ${data.page_count} pages, ${data.chunk_count} searchable chunks.`);
      await loadDocs();
    } catch (e) { setStatus(''); setError(e instanceof Error ? e.message : 'Upload failed.'); }
    finally { setBusy(false); }
  }

  async function ask() {
    if (!selected || !question.trim()) return;
    setBusy(true); setError(''); setStatus('Finding passages and generating an answer…'); setAnswer(''); setCitations([]);
    try {
      const response = await fetch('/api/v1/ask', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: question.trim(), document_ids: [selected], limit: 5 }) });
      const data = await readApiResponse(response);
      if (!response.ok) throw new Error(data.detail || 'Could not answer the question.');
      setAnswer(data.answer); setCitations(data.citations || []); setStatus('Answer ready.');
    } catch (e) { setError(e instanceof Error ? e.message : 'Could not answer the question.'); setStatus(''); }
    finally { setBusy(false); }
  }

  return <section style={{ border: '1px solid #c8d6d2', borderRadius: 12, padding: 18, margin: '0 0 24px', background: '#f7fbf9' }}>
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
      <div><strong>Search your own manual</strong><div style={{ marginTop: 4, color: '#52636a' }}>Upload a PDF here, then ask questions about it without leaving Search.</div></div>
      <button type="button" onClick={() => setOpen(v => !v)} aria-expanded={open}>{open ? 'Hide PDF tools' : 'Upload PDF / Ask a question'}</button>
    </div>
    {open && <div style={{ marginTop: 16 }}>
      <p>PDF only, maximum 10 MB and 300 pages. Scanned pages are processed with Google Document AI OCR. Uploaded manuals are shared with site visitors.</p>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <input type="file" accept="application/pdf,.pdf" onChange={e => setFile(e.target.files?.[0] || null)} aria-label="Choose PDF manual" />
        <button type="button" disabled={!file || busy} onClick={upload}>{busy && !question ? 'Uploading…' : 'Upload PDF'}</button>
      </div>
      <label htmlFor="search-manual-select" style={{ display: 'block', marginTop: 14, fontWeight: 600 }}>Choose an uploaded manual</label>
      <select id="search-manual-select" value={selected} onChange={e => setSelected(e.target.value)} style={{ display: 'block', width: '100%', padding: 9, marginTop: 5 }}>
        <option value="">{docs.some(d => d.status === 'ready') ? 'Select a document' : 'No ready documents yet'}</option>
        {docs.filter(d => d.status === 'ready').map(d => <option key={d.document_id} value={d.document_id}>{d.filename} ({d.page_count} pages)</option>)}
      </select>
      <textarea aria-label="Question about the selected manual" value={question} onChange={e => setQuestion(e.target.value)} placeholder="Ask a question about this manual" rows={3} style={{ display: 'block', width: '100%', margin: '12px 0', padding: 9 }} />
      <button type="button" disabled={busy || !selected || !question.trim()} onClick={ask}>{busy && question ? 'Working…' : 'Ask about this manual'}</button>
      {status && <p role="status">{status}</p>}{error && <p role="alert">{error}</p>}
      {answer && <div><h3>Answer</h3><p style={{ whiteSpace: 'pre-wrap' }}>{answer}</p><h4>Sources</h4><ul>{citations.map((c, i) => <li key={`${c.chunk_id}-${i}`}>{c.filename}, page {c.page_number ?? 'unknown'}</li>)}</ul></div>}
    </div>}
  </section>;
}
