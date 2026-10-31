import io
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException, UploadFile
from starlette.datastructures import Headers

from app.api.routes import documents
from app.models.search import SearchResult
from app.services.embedding import EmbeddingService
from app.services.rag import RAGService


class FakeCollection:
    def __init__(self):
        self.rows = []
        self.updates = []

    def insert_one(self, row):
        self.rows.append(row)

    def insert_many(self, rows, ordered=True):
        self.rows.extend(rows)
        return SimpleNamespace(inserted_ids=list(range(len(rows))))

    def update_one(self, query, update):
        self.updates.append(update["$set"])

    def delete_many(self, query):
        self.rows = [row for row in self.rows if row.get("document_id") != query.get("document_id")]


class DocumentUnitTests(unittest.IsolatedAsyncioTestCase):
    def test_rag_client_requests_vertex_cloud_platform_scope(self):
        from app.core import config
        from app.services import rag
        settings = SimpleNamespace(CHATCOMPLETIONS_MODEL_ID="gemini-test", GCP_PROJECT_ID="project", GCP_CHAT_LOCATION="global")
        service = RAGService.__new__(RAGService)
        service.settings = settings
        with patch.object(rag, "get_settings", return_value=settings), \
             patch.object(rag.google.auth, "default", return_value=(object(), "project")) as auth_default, \
             patch.object(rag.genai, "Client", return_value=object()) as client:
            service._initialize_client()
        auth_default.assert_called_once_with(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        self.assertEqual(client.call_args.kwargs["location"], "global")

    def test_document_ai_ocr_splits_at_processor_page_limit(self):
        from pypdf import PdfWriter
        writer = PdfWriter()
        for _ in range(16): writer.add_blank_page(width=100, height=100)
        data = io.BytesIO(); writer.write(data)
        class FakeResponse:
            def raise_for_status(self): pass
            def json(self): return {"document": {"text": "OCR", "pages": [
                {"layout": {"textAnchor": {"textSegments": [{"startIndex": "0", "endIndex": "3"}]}}}
                for _ in range(15)]}}
        class FakeSession:
            def __init__(self): self.counts = []
            def post(self, url, json, timeout):
                self.counts.append(len(json["rawDocument"]["content"]))
                return FakeResponse()
        session = FakeSession()
        settings = SimpleNamespace(DOCUMENT_AI_PROCESSOR_NAME="projects/p/locations/us/processors/test", DOCUMENT_AI_LOCATION="us")
        with patch.object(documents.google.auth, "default", return_value=(object(), "project")), \
             patch.object(documents, "AuthorizedSession", return_value=session):
            pages = documents._ocr_pdf_pages(data.getvalue(), 16, settings)
        self.assertEqual(len(pages), 16)
        self.assertEqual(len(session.counts), 2)

    async def test_embedding_service_batches_provider_requests(self):
        class FakeModel:
            def __init__(self): self.batch_sizes = []
            async def get_embeddings_async(self, texts):
                self.batch_sizes.append(len(texts))
                return [SimpleNamespace(values=[float(len(texts))]) for _ in texts]
        service = EmbeddingService.__new__(EmbeddingService)
        service.model = FakeModel()
        vectors = await service.generate_embeddings(["text"] * 251)
        self.assertEqual(service.model.batch_sizes, [250, 1])
        self.assertEqual(len(vectors), 251)

    def test_split_page_chunks_text_with_overlap(self):
        text = "word " * 900
        chunks = documents._split_page(text)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(chunks))
        self.assertLessEqual(max(map(len, chunks)), documents.CHUNK_CHARS)

    async def test_rejects_non_pdf_before_database_access(self):
        upload = UploadFile(file=io.BytesIO(b"plain text"), filename="manual.txt", headers=Headers({"content-type": "text/plain"}))
        with patch.object(documents, "get_mongodb") as mongo:
            with self.assertRaises(HTTPException) as caught:
                await documents.upload_pdf(upload)
        self.assertEqual(caught.exception.status_code, 415)
        mongo.assert_not_called()

    async def test_upload_stores_page_chunk_and_marks_document_ready(self):
        settings = SimpleNamespace(MAX_PDF_UPLOAD_MB=10, MAX_PDF_PAGES=300, VECTOR_DIMENSIONS=768, VECTOR_FIELD_NAME="embedding", CHUNKS_COLLECTION="manuals")
        chunks, metadata = FakeCollection(), FakeCollection()
        mongo = SimpleNamespace(get_collection=lambda name: chunks if name == "manuals" else metadata)
        class FakePage:
            def extract_text(self): return "Replace the engine oil filter carefully."
        class FakeReader:
            pages = [FakePage()]
            is_encrypted = False
            def __init__(self, *args, **kwargs): pass
        class FakeEmbedder:
            async def generate_embeddings(self, texts): return [[0.1] * 768 for _ in texts]
        upload = UploadFile(file=io.BytesIO(b"%PDF-1.4 mock"), filename="guide.pdf", headers=Headers({"content-type": "application/pdf"}))
        with patch.object(documents, "get_settings", return_value=settings), \
             patch.object(documents, "get_mongodb", return_value=mongo), \
             patch.object(documents, "PdfReader", FakeReader), \
             patch.object(documents, "EmbeddingService", FakeEmbedder):
            result = await documents.upload_pdf(upload)
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["chunk_count"], 1)
        self.assertEqual(chunks.rows[0]["document_id"], result["document_id"])
        self.assertEqual(chunks.rows[0]["page_numbers"], [1])
        self.assertEqual(len(chunks.rows[0]["embedding"]), 768)
        self.assertEqual(metadata.updates[-1]["status"], "ready")

    async def test_embedding_failure_never_marks_upload_ready(self):
        settings = SimpleNamespace(MAX_PDF_UPLOAD_MB=10, MAX_PDF_PAGES=300, VECTOR_DIMENSIONS=768, VECTOR_FIELD_NAME="embedding", CHUNKS_COLLECTION="manuals")
        chunks, metadata = FakeCollection(), FakeCollection()
        mongo = SimpleNamespace(get_collection=lambda name: chunks if name == "manuals" else metadata)
        class FakePage:
            def extract_text(self): return "Extractable manual text."
        class FakeReader:
            pages = [FakePage()]
            is_encrypted = False
            def __init__(self, *args, **kwargs): pass
        class FailingEmbedder:
            async def generate_embeddings(self, texts): raise RuntimeError("mocked provider failure")
        upload = UploadFile(file=io.BytesIO(b"%PDF-1.4 mock"), filename="guide.pdf", headers=Headers({"content-type": "application/pdf"}))
        with patch.object(documents, "get_settings", return_value=settings), \
             patch.object(documents, "get_mongodb", return_value=mongo), \
             patch.object(documents, "PdfReader", FakeReader), \
             patch.object(documents, "EmbeddingService", FailingEmbedder):
            with self.assertRaises(HTTPException) as caught:
                await documents.upload_pdf(upload)
        self.assertEqual(caught.exception.status_code, 502)
        self.assertEqual(metadata.updates[-1]["status"], "failed")
        self.assertFalse(chunks.rows)

    async def test_question_uses_selected_document_and_returns_page_citation(self):
        settings = SimpleNamespace(VECTOR_DIMENSIONS=768, DOCUMENT_VECTOR_INDEX_NAME="manual_documents_vector_index",
                                   CHUNKS_COLLECTION="manuals")
        class FakeDocs:
            def find(self, query, projection): return [{"document_id": "selected"}]
        collections = {"manuals": object(), documents.DOCUMENTS_COLLECTION: FakeDocs()}
        mongo = SimpleNamespace(get_collection=lambda name: collections[name])
        class FakeEmbedder:
            async def generate_embedding(self, question): return [0.0] * 768
        class FakeSearch:
            def __init__(self): pass
            async def vector_search(self, **kwargs):
                self.kwargs = kwargs
                return [SearchResult(score=0.9, chunk_id="selected:1", document_id="selected",
                    source_filename="manual.pdf", text="Change the oil filter.", page_numbers=[7])]
        search = FakeSearch()
        answers = {"result": None}
        class FakeRAG:
            async def generate_answer(self, question, chunks):
                answers["result"] = (question, chunks)
                return "Change the filter as described."
        with patch.object(documents, "get_settings", return_value=settings), \
             patch.object(documents, "get_mongodb", return_value=mongo), \
             patch.object(documents, "EmbeddingService", FakeEmbedder), \
             patch.object(documents, "SearchRepository", return_value=search), \
             patch.object(documents, "RAGService", FakeRAG):
            result = await documents.ask_document(documents.AskRequest(question="How do I change it?", document_ids=["selected"]))
        self.assertEqual(search.kwargs["document_ids"], ["selected"])
        self.assertEqual(search.kwargs["index_name"], "manual_documents_vector_index")
        self.assertEqual(result["answer"], "Change the filter as described.")
        self.assertEqual(result["citations"][0]["filename"], "manual.pdf")
        self.assertEqual(result["citations"][0]["page_number"], 7)

    async def test_rag_prompt_contains_only_selected_source_and_returns_answer(self):
        class FakeModels:
            def generate_content(self, **kwargs):
                self.request = kwargs
                return SimpleNamespace(text="The manual says to replace the filter. [manual.pdf, page 7]")
        service = RAGService.__new__(RAGService)
        service.model_id = "gemini-mock"
        service.client = SimpleNamespace(models=FakeModels())
        chunk = ChunkForTest()
        answer = await service.generate_answer("How do I replace it?", [chunk])
        self.assertIn("manual.pdf", service.client.models.request["contents"])
        self.assertIn("page(s): 7", service.client.models.request["contents"])
        self.assertEqual(answer, "The manual says to replace the filter. [manual.pdf, page 7]")


class ChunkForTest:
    text = "Replace the filter using the stated procedure."
    source_filename = "manual.pdf"
    page_numbers = [7]
    breadcrumb_trail = None
    heading_level_1 = None
    heading_level_2 = None
    heading_level_3 = None
    safety_notices = []
    procedural_steps = []


if __name__ == "__main__":
    unittest.main()
