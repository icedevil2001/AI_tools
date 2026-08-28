# # Gene Searcher v1.0


import os
import json
import sqlite3
import urllib.parse
import requests
import openai
from bs4 import BeautifulSoup
# from pydantic import BaseModel, Field as Field_
import pydantic as pyd
from typing import Optional
from dotenv import load_dotenv
from rich import print


from sqlmodel import Field, Session, SQLModel, create_engine, select
from duckduckgo_search import DDGS

results = DDGS().text("FASN hypomethylated cancer", max_results=5)
print(results)


load_dotenv()
# Set your OpenAI API key
openai.api_key = os.getenv("OPENAI_API_KEY")  # or directly assign your key string

from openai import OpenAI

# Initialize OpenAI client
client = OpenAI()


class GeneMethylationInfo(pyd.BaseModel):
    Gene_name: str = pyd.Field(None, description="The name of the gene")
    methylation_status: Optional[str] = pyd.Field(
        None, description="Hypermethylated or Hypomethylated"
    )
    phenotype: Optional[str] = pyd.Field(
        None, description="Phenotypic description related to methylation"
    )
    gene_function: Optional[str] = pyd.Field(
        None, description="Function of the gene in the cell"
    )
    role_in_cancer: Optional[str] = pyd.Field(
        None, description="Role of the gene in cancer"
    )
    Disease: Optional[str] = pyd.Field(None, description="Associated disease(s)")
    url: str = pyd.Field(None, description="URL of the source")


# -------------------------------
# Database (SQLite) Setup Functions
# -------------------------------
DB_FILENAME = "gene_methylation.db"
sqlite_url = f"sqlite:///{DB_FILENAME}"
engine = create_engine(sqlite_url)

class GeneTable(SQLModel, table=True):
    __tablename__ = "gene_methylation"
    __table_args__ = {"extend_existing": True}
    
    gene: str = Field(primary_key=True)
    methylation_status: Optional[str] = None
    phenotype: Optional[str] = None
    role_in_cancer: Optional[str] = None
    disease: Optional[str] = None

def init_db():
    SQLModel.metadata.create_all(engine)


def get_cached_gene_info(gene: str) -> Optional[GeneMethylationInfo]:
    with Session(engine) as session:
        statement = select(GeneTable).where(GeneTable.gene == gene)
        result = session.exec(statement).first()
        if result:
            return GeneMethylationInfo(
                Gene_name=result.gene,
                methylation_status=result.methylation_status,
                phenotype=result.phenotype,
                role_in_cancer=result.role_in_cancer,
                Disease=result.disease
            )
    return None

def save_gene_info_to_cache(gene_info: GeneMethylationInfo):
    with Session(engine) as session:
        gene_record = GeneTable(
            gene=gene_info.Gene_name,
            methylation_status=gene_info.methylation_status,
            phenotype=gene_info.phenotype,
            role_in_cancer=gene_info.role_in_cancer,
            disease=gene_info.Disease
        )
        session.merge(gene_record)
        session.commit()


def search_gene_info(gene: str, methylation_status: str, search_query: str, max_results: int = 5) -> list:
    query = f"{gene} {methylation_status} {search_query} cancer"
    results = DDGS().text(query, max_results=max_results)
    return results

def find_best_results(results: list[dict[str, str]]) -> str:
    """Use small OpenAI to find best result."""
    # Combine all search results into a single text
    combined_text = ""
    for result in results:
        title = result.get('title', '')
        body = result.get('body', '')
        url = result.get('url', '')
        combined_text += f"Title: {title}\nContent: {body}\n\n url: {url}\n\n"
    
    if not combined_text:
        return "No relevant information found."
    
    prompt = f"""
    Analyze the following search results and extract relevant information about gene methylation, 
    its role in cancer, and associated phenotypes. Focus on methylation status and disease relationships:

    {combined_text}

    Please provide a concise summary of the most relevant findings. and associated phenotypes. Focus on methylation status and disease relationships.
    
    """
    
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a scientific literature analyzer focusing on gene methylation in cancer."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=2000,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Error in processing search results: {e}")
        return "Error processing search results."



def extract_methylation_info_with_openai(text: str, gene: str) -> GeneMethylationInfo:
    """
    Uses the OpenAI API to extract methylation information.
    The prompt instructs the model to return a JSON object with the keys:
    Gene_name, methylation_status, phenotype, role_in_cancer, Disease.
    """
    prompt = f"""
    You are an expert in molecular biology and cancer research. Given the following text, extract the following information about the gene "{gene}":
    """ 
    response = client.beta.chat.completions.parse(
        model="gpt-4",
        messages=[
            {
                "role": "system",
                "content": "You extract specific scientific data from text.",
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
        max_tokens=500,
        response_format=GeneMethylationInfo,
    )
    # Parse the returned JSON and create a GeneMethylationInfo instance
    # json_response = json.loads(response.choices[0].message.content.strip())
    return response

def run_workflow():
    # Initialize the database (creates the table if it doesn't exist)
    init_db()

    genes_to_analyze = ["FASN", "TP53", "BRCA1"]
    methylated_status = ["hypermethylated", "methylated", "hypermethylated"]

    for gene, methyl_status in zip(genes_to_analyze, methylated_status):
        # Check if the gene's information is already cached.
        cached_info = get_cached_gene_info(gene)
        if cached_info:
            print(f"Returning cached information for {gene}.")
            print(cached_info)
            continue

        # Search for relevant URLs.
        urls = search_gene_info(gene, methyl_status, "cancer", max_results=5)
        print(urls)
        result = find_best_results(urls)
        print(result)
        final_output = extract_methylation_info_with_openai(result, gene)
        print(final_output)
        
        break

run_workflow()

# # %%
# # url = "https://pmc.ncbi.nlm.nih.gov/articles/PMC9779179/"
# url = "https://pmc.ncbi.nlm.nih.gov/articles/PMC9779179/"

# # bs4 = BeautifulSoup(requests.get(url).text, "html.parser")
# # print(bs4.title.text)
# # print(bs4.get_text())

# response = requests.get(url, timeout=5, headers={"User-Agent": "Mozilla/5.0"})
# print(response.status_code)
# if response.status_code == 200:
#     soup = BeautifulSoup(response.text, "html.parser")
#     page_text = soup.get_text(separator=" ", strip=True)
#     print(page_text)
