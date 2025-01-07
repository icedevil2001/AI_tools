import os 
import tempfile
from pathlib import Path
import yaml

import chromadb 
import ollama
import streamlit as st
from chromadb.utils.embedding_functions.ollama_embedding_function import (
    OllamaEmbeddingFunction,
)
from langchain_community.document_loaders import PyMuPDFLoader
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from sentence_transformers import CrossEncoder
from streamlit.runtime.uploaded_file_manager import UploadedFile

from loguru import logger
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()


def load_config(config_path="config.yaml"):
    """Loads the configuration file for the application.

    Args:
        config_path: Path to the configuration file. Defaults to "config.yaml".

    Returns:
        dict: A dictionary containing the configuration settings.
    """
    with open(config_path, "r") as file:
        return yaml.safe_load(file)


def load_topics(topics_file="topics.yaml"):
    """Load topics from a YAML file."""
    if Path(topics_file).exists():
        with open(topics_file, "r") as f:
            return yaml.safe_load(f)
        
    return ["General"]  # default topics if file doesn't exist

def save_topics(topics, topics_file="topics.yaml"):
    """Save topics to a YAML file."""
    with open(topics_file, "w") as f:
        yaml.safe_dump(list(set(topics)), f)


def get_models(config: dict ):
    """Get a list of available models from config file"""
    models = {}
    for company in config["LLM"]:
        models[company] = {
            "models": config["LLM"][company]["models"],
            "base_url": config["LLM"][company]["base_url"]
            }
    return models


def process_document(uploaded_file: UploadedFile, config) -> list[Document]:
    """Processes an uploaded PDF file by converting it to text chunks.

    Takes an uploaded PDF file, saves it temporarily, loads and splits the content
    into text chunks using recursive character splitting.

    Args:
        uploaded_file: A Streamlit UploadedFile object containing the PDF file

    Returns:
        A list of Document objects containing the chunked text from the PDF

    Raises:
        IOError: If there are issues reading/writing the temporary file
    """
    # Store uploaded file as a temp file
    temp_file = tempfile.NamedTemporaryFile("wb", suffix=".pdf", delete=False)
    temp_file.write(uploaded_file.read())

    loader = PyMuPDFLoader(temp_file.name)
    docs = loader.load()
    os.unlink(temp_file.name)  # Delete temp file

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=config["text_splitter"]["chunk_size"],
        chunk_overlap=config["text_splitter"]["chunk_overlap"],
        separators=config["text_splitter"]["separators"],
        # ["\n\n", "\n", ".", "?", "!", " ", ""],
    )
    return text_splitter.split_documents(docs)


# Based on https://docs.trychroma.com/usage-guide

# import chromadb

# persist_directory = '/tmp/vector_db'
# client = chromadb.PersistentClient(path=persist_directory)

# collection2 = client.create_collection( \
#        name="save_embeddings", \
#        metadata={"hnsw:space": "cosine"} # l2 is the default \
#    )

# collection2.add( \
#    embeddings=[[1.1, 2.3, 3.2], [4.5, 6.9, 4.4], [1.1, 2.3, 3.2]], \
#    metadatas=[{"chapter": "3", "verse": "16"}, {"chapter": "3", "verse": "5"}, {"chapter": "29", "verse": "11"}], \
#    ids=["id1", "id2", "id3"] \
# )

# # To query
# collection2 = client.get_collection(name="save_embeddings")

# collection2.query( \
#     query_embeddings=[[11.1, 12.1, 13.1]], \
#     n_results=10, \
#     # where={"metadata_field": "is_equal_to_this"}, \
#     # where_document={"$contains":"search_string"} \
# )



def get_vector_collection(topic: str) -> chromadb.Collection:
    """Gets or creates a ChromaDB collection for vector storage.

    Creates an Ollama embedding function using the nomic-embed-text model and initializes
    a persistent ChromaDB client. Returns a collection that can be used to store and
    query document embeddings.
    
    for semantic search. see https://stackoverflow.com/questions/77794024/searching-existing-chromadb-database-using-cosine-similarity 
    options: 
        - cosine
        - euclidean
        - l2 (square root of the sum of the squares)
        - ip (inner product)

        for reseach paper use cosine similarity

    Returns:
        chromadb.Collection: A ChromaDB collection configured with the Ollama embedding
            function and cosine similarity space.
    """
    ollama_ef = OllamaEmbeddingFunction(
        url="http://localhost:11434/api/embeddings",
        model_name="nomic-embed-text:latest",
    )

    chroma_client = chromadb.PersistentClient(path="./vector_db")
    return chroma_client.get_or_create_collection(
        name=f"rag_{topic}",
        embedding_function=ollama_ef,
        metadata={"hnsw:space": "cosine"}, # Use cosine similarity for semantic search
    )


def add_to_vector_collection(all_splits: list[Document], file_name: str, topic: str):
    """Adds document splits to a vector collection for semantic search.

    Takes a list of document splits and adds them to a ChromaDB vector collection
    along with their metadata and unique IDs based on the filename.

    Args:
        all_splits: List of Document objects containing text chunks and metadata
        file_name: String identifier used to generate unique IDs for the chunks

    Returns:
        None. Displays a success message via Streamlit when complete.

    Raises:
        ChromaDBError: If there are issues upserting documents to the collection
    """
    collection = get_vector_collection(topic)
    documents, metadatas, ids = [], [], []

    for idx, split in enumerate(all_splits):
        documents.append(split.page_content)
        metadatas.append(split.metadata)
        ids.append(f"{file_name}_{idx}")

    try:
        collection.upsert(
            documents=documents,
            metadatas=metadatas,
            ids=ids,
        )
        st.success("Data added to the vector store!")
    except Exception as e:
        st.error(f"Failed to add data to the vector store: {e}")


def query_collection(prompt: str, n_results: int = 10, topic="General") -> dict:
    """Queries the vector collection with a given prompt to retrieve relevant documents.

    Args:
        prompt: The search query text to find relevant documents.
        n_results: Maximum number of results to return. Defaults to 10.

    Returns:
        dict: Query results containing documents, distances and metadata from the collection.

    Raises:
        ChromaDBError: If there are issues querying the collection.
    """
    collection = get_vector_collection(topic=topic)
    results = collection.query(query_texts=[prompt], n_results=n_results)
    return results


def call_llm(api_key: str, model: str, base_url: str, context: str, prompt: str, system_prompt: str):
    """Calls the language model with context and prompt to generate a response.

    Uses Ollama to stream responses from a language model by providing context and a
    question prompt. The model uses a system prompt to format and ground its responses appropriately.

    Args:
        context: String containing the relevant context for answering the question
        prompt: String containing the user's question

    Yields:
        String chunks of the generated response as they become available from the model

    Raises:
        OllamaError: If there are issues communicating with the Ollama API
    """
    # response = ollama.chat(
    #     model=model,
    #     stream=True,
    #     messages=[
    #         {
    #             "role": "system",
    #             "content": system_prompt,
    #         },
    #         {
    #             "role": "user",
    #             "content": f"Context: {context}, Question: {prompt}",
    #         },
    #     ],
    # )
    # for chunk in response:
    #     if chunk["done"] is False:
    #         yield chunk["message"]["content"]
    #     else:
    #         break
    llm_client = OpenAI(
        api_key=api_key,
        base_url=base_url
        )
    response = llm_client.chat.completions.create(
        model=model,
        stream=True,
        messages=[
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": f"Context: {context}, Question: {prompt}",
            },
        ],
    )
    # print(response)
    for chunk in response:
        # print(chunk)
        if chunk.choices[0].delta.content is None:
            break
        yield chunk.choices[0].delta.content 



def re_rank_cross_encoders(documents: list[str]) -> tuple[str, list[int]]:
    """Re-ranks documents using a cross-encoder model for more accurate relevance scoring.

    Uses the MS MARCO MiniLM cross-encoder model to re-rank the input documents based on
    their relevance to the query prompt. Returns the concatenated text of the top 3 most
    relevant documents along with their indices.

    Args:
        documents: List of document strings to be re-ranked.

    Returns:
        tuple: A tuple containing:
            - relevant_text (str): Concatenated text from the top 3 ranked documents
            - relevant_text_ids (list[int]): List of indices for the top ranked documents

    Raises:
        ValueError: If documents list is empty
        RuntimeError: If cross-encoder model fails to load or rank documents
    """
    relevant_text = ""
    relevant_text_ids = []

    encoder_model = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
    ranks = encoder_model.rank(prompt, documents, top_k=3)
    for rank in ranks:
        relevant_text += documents[rank["corpus_id"]]
        relevant_text_ids.append(rank["corpus_id"])

    return relevant_text, relevant_text_ids


if __name__ == "__main__":
    # Document Upload Area
    config  =load_config()
    SYSTEM_PROMPT = config["system_prompt"]
    MODEL = config['ollama']["model"]
    # st.title("🔍 RAG Question Answering System")
    with st.sidebar:
        st.set_page_config(page_title="RAG Question Answer")
        uploaded_files = st.file_uploader(
            "**📑 Upload PDF files for QnA**", type=["pdf"], accept_multiple_files=True
        )

        process = st.button(
            "⚡️ Process",
        )
        topics = load_topics()

        companies  = get_models(config)
        selected_company = st.selectbox("AI Company", list(companies.keys()))
        selected_model = st.selectbox("LLM Model", companies[selected_company]["models"])
        base_url = companies[selected_company]["base_url"]
        LLM_API_KEY = os.getenv(config["LLM"][selected_company]['env']["api_key"], None)
        if not LLM_API_KEY:
            LLM_API_KEY = st.text_input("LLM API KEY", type='password')
            st.warning(f"Please set the {config["LLM"][selected_company]['env']["api_key"]} in the environment variable")


        selected_topic = st.selectbox("Select Topic", topics)
        new_topic = st.text_input("Or create a new topic").strip().title()
        if st.button("Add Topic"):
            topics.append(new_topic)
            save_topics(topics)
            st.success(f"'{new_topic}' added!")
            selected_topic = new_topic
        
        if uploaded_files and process:
            for uploaded_file in uploaded_files:
                normalize_uploaded_file_name = uploaded_file.name.translate(
                    str.maketrans({"-": "_", ".": "_", " ": "_"})
                )
                all_splits = process_document(uploaded_file, config)
                add_to_vector_collection(all_splits, normalize_uploaded_file_name, selected_topic)

        num_results = st.number_input("Number of results to show", min_value=1, value=100, step=1)

        
    # Question and Answer Area
    st.header("🗣️ RAG Question Answer")
    prompt = st.text_area("**Ask a question related to your document:**")
    ask = st.button(
        "🔥 Ask",
    )

    if ask and prompt:
        results = query_collection(prompt, n_results=num_results, topic=selected_topic)
        print(">>>", results)
        context = results.get("documents")[0]
        relevant_text, relevant_text_ids = re_rank_cross_encoders(context)
        response = call_llm(
            api_key=LLM_API_KEY,
            model=selected_model,
            context=relevant_text,
            base_url=base_url,
            prompt=prompt,
            system_prompt=SYSTEM_PROMPT)
        
        st.write_stream(response)

        with st.expander("See retrieved documents"):
            st.write(results)

        with st.expander("See most relevant document ids"):
            st.write(relevant_text_ids)
            st.write(relevant_text)