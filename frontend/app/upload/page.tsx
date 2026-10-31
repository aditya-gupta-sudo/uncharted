'use client';

import { useEffect, useState } from 'react';

type DocumentInfo = { document_id: string; filename: string; status: string; chunk_count: number; page_count: number };
type Answer = { question: string; answer: string; citations: { filename: string; page_number: number | null; chunk_id: string; score: number }[]; sources: { text: string; filename?: string; source_filename?: string; page_numbers?: number[] }[] };

export default function UploadPage() {
  const [documents, setDocuments] = useState<DocumentInfo[]>([]);
  const [selected, setSelected] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [documentsLoading, setDocumentsLoading] = useState(true);
  const [documentError, setDocumentError] = useState('');

  async function refreshDocuments() {
    setDocumentsLoading(true);
    setDocumentError('');
    try {
      const response = await fetch('/api/v1/documents', { cache: 'no-store' });
      if (!response.ok) throw new Error(`Could not load documents (HTTP ${response.status}).`);
      const result: unknown = await response.json();
      if (!Array.isArray(result)) throw new Error('The documents endpoint returned an unexpected response.');
      setDocuments(result);
    } catch (error) {
      const reason = error instanceof Error ? error.message : 'Could not load documents.';
      setDocumentError(`${reason} Check that the backend is deployed and the frontend INTERNAL_API_URL points to it.`);
      throw error;
    } finally {
      setDocumentsLoading(false);
    }
  }

  useEffect(() => { refreshDocuments().catch(error => setMessage(error.message)); }, []);

  async function upload() {
    if (!file) return;
    setBusy(true); setMessage('Uploading and processing PDF…'); setAnswer(null);
    try {
      const form = new FormData(); form.append('file', file);
      const response = await fetch('/api/v1/documents/upload', { method: 'POST', body: form });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail || 'Upload failed.');
      setMessage(`Upload complete: ${body.filename} — ${body.page_count} pages and ${body.chunk_count} searchable chunks.`);
      setSelected(body.document_id); setFile(null); await refreshDocuments().catch(() => {});
    } catch (error) { setMessage(error instanceof Error ? error.message : 'Upload failed.'); }
    finally { setBusy(false); }
  }

  async function ask() {
    if (!question.trim() || !selected) return;
    setBusy(true); setMessage('Finding relevant passages and generating an answer…'); setAnswer(null);
    try {
      const response = await fetch('/api/v1/ask', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: question.trim(), document_ids: [selected], limit: 5 }) });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail || 'Could not answer this question.');
      setAnswer(body); setMessage('');
    } catch (error) { setMessage(error instanceof Error ? error.message : 'Could not answer this question.'); }
    finally { setBusy(false); }
  }

  return <main style={{ maxWidth: 900, margin: '40px auto', padding: 24, fontFamily: 'Arial, sans-serif' }}>
    <h1>PDF Manual Q&amp;A</h1>
    <p>Uploaded PDFs are shared with all visitors to this site. Do not upload private or sensitive documents.</p>
    <section style={{ border: '1px solid #ccc', borderRadius: 8, padding: 20, marginBottom: 24 }}>
      <h2>Upload a PDF</h2>
      <input type="file" accept="application/pdf,.pdf" onChange={event => setFile(event.target.files?.[0] || null)} />
      <button disabled={!file || busy} onClick={upload} style={{ marginLeft: 12 }}>Upload PDF</button>
      <p>PDF only, maximum 10 MB and 300 pages. Scanned pages are processed with Google Document AI OCR.</p>
    </section>
    <section style={{ border: '1px solid #ccc', borderRadius: 8, padding: 20 }}>
      <h2>Ask about a document</h2>
      <label htmlFor="document-select" style={{ display: 'block', margin: '12px 0 6px', fontWeight: 600 }}>Choose a document</label>
      <select id="document-select" aria-label="Choose a document" value={selected} disabled={documentsLoading || busy || !documents.some(doc => doc.status === 'ready')}
        onChange={event => setSelected(event.target.value)} style={{ display: 'block', width: '100%', padding: 10 }}>
        <option value="">{documentsLoading ? 'Loading documents…' : documents.some(doc => doc.status === 'ready') ? 'Select a document' : 'No ready documents available'}</option>
        {documents.filter(doc => doc.status === 'ready').map(doc => <option key={doc.document_id} value={doc.document_id}>
          {doc.filename} ({doc.page_count} pages, {doc.chunk_count} chunks)
        </option>)}
      </select>
      {documentError && <p role="alert">{documentError} <button type="button" onClick={() => refreshDocuments().catch(() => {})}>Retry</button></p>}
      {!documentsLoading && !documentError && documents.length === 0 && <p>No documents yet. Upload a text-based PDF above to get started.</p>}
      <textarea value={question} onChange={event => setQuestion(event.target.value)} placeholder="Ask a question about the selected PDF" rows={3} style={{ display: 'block', width: '100%', margin: '16px 0' }} />
      <button disabled={busy || !selected || !question.trim()} onClick={ask}>{busy && question.trim() ? 'Working…' : 'Ask'}</button>
    </section>
    {message && <p role="status">{message}</p>}
    {answer && <section style={{ marginTop: 24 }}><h2>Answer</h2><p style={{ whiteSpace: 'pre-wrap' }}>{answer.answer}</p>
      <h3>Sources</h3><ul>{answer.citations.map((citation, index) => <li key={`${citation.chunk_id}-${index}`}>{citation.filename}, page {citation.page_number ?? 'unknown'}</li>)}</ul>
      <details><summary>Retrieved chunks</summary>{answer.sources.map((source, index) => <article key={index}><h4>{source.source_filename || source.filename} — page {(source.page_numbers || []).join(', ')}</h4><p>{source.text}</p></article>)}</details>
    </section>}
  </main>;
}
