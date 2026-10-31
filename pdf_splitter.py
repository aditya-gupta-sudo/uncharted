
from PyPDF2 import PdfReader, PdfWriter
import os
import math

def split_pdf_for_document_ai(
    input_pdf_path,
    output_dir,
    pages_per_chunk=15, # Reduced default for safety margin
    start_page_number=1 # 1-based page number to start processing from
    ):
    """
    Split a PDF into smaller chunks for Document AI processing, optionally skipping initial pages.

    Args:
        input_pdf_path: Path to the input PDF file.
        output_dir: Directory to save the split PDF files.
        pages_per_chunk: Number of pages per chunk.
        start_page_number: The 1-based page number to start splitting from.

    Returns:
        Tuple: (List of paths to the split PDF files, total_pages_processed)
    """
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    pdf_name = os.path.splitext(os.path.basename(input_pdf_path))[0]

    try:
        pdf = PdfReader(input_pdf_path)
        total_source_pages = len(pdf.pages)
    except Exception as e:
        print(f"Error reading PDF {input_pdf_path}: {e}")
        return [], 0

    # Adjust for 0-based indexing and calculate the first page index to include
    start_page_index = max(0, start_page_number - 1)

    if start_page_index >= total_source_pages:
        print(f"Warning: Start page ({start_page_number}) is beyond the total number of pages ({total_source_pages}). No pages to process.")
        return [], 0

    # Calculate the number of pages to actually process
    pages_to_process_count = total_source_pages - start_page_index
    num_chunks = math.ceil(pages_to_process_count / pages_per_chunk)

    chunk_paths = []
    total_pages_processed_in_chunks = 0

    print(f"Source PDF has {total_source_pages} pages. Processing from page {start_page_number} ({pages_to_process_count} pages).")
    print(f"Splitting into {num_chunks} chunks of up to {pages_per_chunk} pages each.")

    for i in range(num_chunks):
        output = PdfWriter()

        # Calculate start and end page indices relative to the *source* PDF
        chunk_start_index_rel_processed = i * pages_per_chunk
        chunk_end_index_rel_processed = min((i + 1) * pages_per_chunk, pages_to_process_count)

        # Map back to source page indices
        source_start_page_index = start_page_index + chunk_start_index_rel_processed
        source_end_page_index = start_page_index + chunk_end_index_rel_processed

        pages_in_this_chunk = 0
        for page_num_idx in range(source_start_page_index, source_end_page_index):
            # Ensure we don't go beyond the actual number of pages
            if page_num_idx < total_source_pages:
                try:
                    output.add_page(pdf.pages[page_num_idx])
                    pages_in_this_chunk += 1
                except Exception as e:
                     print(f"Error adding page {page_num_idx + 1} to chunk {i+1}: {e}")


        if pages_in_this_chunk > 0:
            output_path = os.path.join(output_dir, f"{pdf_name}_chunk_{i+1}_pages_{source_start_page_index+1}-{source_end_page_index}.pdf")
            try:
                with open(output_path, "wb") as output_file:
                    output.write(output_file)
                chunk_paths.append(output_path)
                total_pages_processed_in_chunks += pages_in_this_chunk
                print(f"Created chunk {i+1}/{num_chunks}: pages {source_start_page_index+1}-{source_end_page_index} -> {output_path}")
            except Exception as e:
                print(f"Error writing chunk {i+1} to {output_path}: {e}")
        else:
            print(f"Skipping chunk {i+1} as it contains no valid pages.")


    print(f"Finished splitting. Total pages included in chunks: {total_pages_processed_in_chunks}")
    return chunk_paths, total_pages_processed_in_chunks
