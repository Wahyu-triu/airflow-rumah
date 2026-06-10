import sys
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent
sys.path.append(str(root_dir))

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from embedding_properties.embed_properties import search_property
from langchain_core.runnables import RunnableLambda
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import StrOutputParser
from functools import partial
from chatbot_utils import retrieve_message

from dotenv import load_dotenv
import os
load_dotenv()

OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
DB_CONN  = os.environ["PROPERTY_DB_CONN"]

llm = ChatOpenAI(
    model="gpt-4.1-mini",
    temperature=0.25
)

def retrieve_context_property(inputs, db_conn=DB_CONN):
    question = inputs["question"]
    docs = search_property(db_conn=db_conn, question=question)

    context = "\n\n".join([
        doc[1]
        for doc in docs
    ])

    return {
        "question": question,
        "context": context,
        "chat_history": inputs["chat_history"],
    }

def retrieve_context_knowledge(inputs):
    question = inputs["question"]
    context = """
        Anda disini berperan sebagai seseorang yang sangat expert dalam bidang properti dan agency.
        Anda sangat menguasai tentang jual beli properti, pengurusan dokumen jual beli, KPR, dan hal-hal lain yang biasanya berkaitan dengan transaksi properti.

        Anda tidak perlu data properti tambahan, HANYA gunakan data dari CHAT_HISTORY
    """

    return {
        "question": question,
        "context": context,
        "chat_history": inputs["chat_history"],
    }

def load_chat_histories(inputs):
    chat_id = inputs["chat_id"]

    chat_histories = retrieve_message(chat_id)

    print('-' * 10)
    print('CHAT HISTORIES')
    print(chat_histories)
    print('-' * 10)

    return ({
        'question' : inputs['question'],
        'chat_id' : inputs['chat_id'],
        'chat_history' : chat_histories
    })

def route_decision(inputs, router_chain):
    # Run the router chain using the inputs
    decision = router_chain.invoke({
        "chat_history": inputs["chat_history"],
        "question": inputs["question"]
    })
    print('=' * 10)
    print(decision)
    print('=' * 10)
    
    # Choose which chain to execute based on the classification
    if decision == "DETAIL":
        print("--- ROUTING TO DETAIL PATH ---")
        retrieval_knowledge_callable = partial(retrieve_context_knowledge)
        return RunnableLambda(retrieval_knowledge_callable)
        
    else:
        print("--- ROUTING TO SEARCH PATH ---")
        retrieval_property_callable = partial(retrieve_context_property, db_conn=DB_CONN)
        return RunnableLambda(retrieval_property_callable)


def rag_query(inputs, llm=llm):
    # Style Prompt
    style_prompt = """
                    # ROLE
                    Anda adalah AI Assistant ahli di bidang properti (khususnya hunian/tempat tinggal) di Indonesia.

                    # GAYA KOMUNIKASI
                    1. Karakter Anda adalah seorang teman yang realistis, solutif, dan asik. karena akrab, jadi biasa menggunakan bahasa informal
                    2. Gunakan gaya komunikasi yang natural seperti mengobrol dichatingan dengan teman. 
                    3. JANGAN PERNAH menggunakan akhiran kalimat seperti sales, seperti: 'sekitarnya ya! Kalau ada yang mau ditanya lebih lanjut, silakan aja!'. 
                """
    # Search prompt
    search_prompt = """
                    # TUGAS UTAMA
                    Tugasmu adalah **memberikan rekomendasi atau pilihan properti** yang cocok berdasarkan permintaan pengguna menggunakan data dari <konteks_data>. Berikan beberapa opsi yang tersedia secara santai.
    
                    # BATASAN & ATURAN (GUARDRAILS)
                    1. Kepatuhan pada Konteks: Anda HANYA BOLEH memberikan rekomendasi properti yang datanya bersumber dari <konteks_data>. Jangan mengada-ada atau mengambil data properti eksternal di luar database yang diberikan.
                    2. Penanganan Data Kosong: Jika properti yang dicari pengguna tidak ditemukan di dalam <konteks_data>, jawablah dengan jujur dan ramah bahwa Anda belum memiliki data tersebut (misal: "Wah, maaf banget, untuk daerah itu datanya belum masuk di sistem aku nih...").
                    3. Jika anda diminta memberikan pendapat tentang properti, anda boleh memberikan penilaian sesuai dengan expertise anda.
                    4. Jika menggunakan history chat/perbincangan sebagai data, utama histori perbincangan yang paling baru (sudah diurutkan dari paling atas).
                    5. Batasan Topik Luar: Tolak secara halus jika pengguna bertanya di luar topik properti Indonesia.
                    6. Focus Geografis: Hanya melayani wilayah Indonesia.
                    7. Format Teks: JANGAN menggunakan markdown formatting seperti double asterisks (**) untuk menebalkan teks. Tuliskan judul properti dan nama detailnya (seperti Lokasi, Harga, Kamar Tidur) secara polos/clean tanpa simbol dekoratif apapun.
                """
    
    # Route prompt
    route_prompt = ChatPromptTemplate.from_messages([
                ("system", """Analisis input pengguna dan riwayat obrolan untuk menentukan langkah berikutnya.
                    
                    Pilih 'SEARCH' jika:
                    - User MENCARI dan MEMINTA rekomendasi properti baru (misal: "cari rumah di Bogor", "ada apartemen murah?").
                    - User MEMINTA data properti lain sebagai pembanding. 

                    Pilih 'DETAIL' jika:
                    - User menanyakan detail lebih lanjut tentang properti tertentu yang SUDAH disebutkan oleh AI di chat history (misal: "tolong jelasin yang ini dong", "lokasi persisnya di mana?", "skema KPR-nya gimana?", "ambil yang opsi pertama dong").
                    - User mengajak DISKUSI (misal: "menurut kamu bagus nggak?", "kalo untuk orang kerja kantoran bagus nggak ya?", "ramah anak kecil nggak ya?")
                    - User meminta PENDAPAT (misal: "menurut lo kualitasnya oke nggak?", "buat harga segitu bagu apa enggak?")

                    ATURAN MENJAWAB:
                    - jawab "SEARCH" atau "DETAIL". JANGAN PERNAH MENAMBAHKAN KALIMAT APAPUN.
                    
                    """),
                    ("placeholder", "{chat_history}"),
                    ("human", "{question}")
                ])

    # Router Chain (Wheter a search or detail question)
    router_chain = (
                    route_prompt 
                    | llm 
                    | StrOutputParser()
                )

    # Runnable route_decision
    route_decision_callable = partial(route_decision, router_chain=router_chain)
    
    
    compiled_prompt = ChatPromptTemplate.from_messages([
                            ("system",  (style_prompt + "\n\n" + search_prompt)),
                            ("system", "<history chat>\n"),
                            MessagesPlaceholder(variable_name="chat_history"),
                            ("system", "<history chat>\n"),
                            ("system", "Konteks data properti:\n<konteks>\n{context}\n<konteks>\n"),
                            ("human", "<pertanyaan>\n{question}\n<pertanyaan>")
                        ])
    
    chain = (
        RunnableLambda(load_chat_histories)
        | RunnableLambda(route_decision_callable)
        | compiled_prompt
        | llm
    )

    response = chain.invoke(inputs)
    return response.content