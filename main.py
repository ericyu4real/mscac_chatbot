from flask import Flask, request
from langchain.chains import RetrievalQA, ConversationalRetrievalChain
from langchain.memory import ConversationBufferMemory
from langchain_community.chat_models import ChatOpenAI
from langchain.prompts import PromptTemplate
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings
import os
from flask_cors import CORS
from flask import jsonify
import json
from datetime import datetime
import pytz

app = Flask(__name__)
CORS(app)

# read env variables
openaikey = os.environ['OPENAI_API_KEY']
uri = os.environ['mongodb']

#mangodb setup
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
client = MongoClient(uri, server_api=ServerApi('1'))

#vectordb setup
embeddings = OpenAIEmbeddings()
db = FAISS.load_local("faiss_index",
                      embeddings,
                      allow_dangerous_deserialization=True)

# Build prompt
template = """You are a helpful AI assistant working for MScAC (The Master of Science in Applied Computing) at the University of Toronto, the best CS master program in Canada. This program offers a unique combination of academic research and industry engagement. The program aims to cultivate world-class innovators through rigorous education in state-of-the-art research techniques, culminating in an applied research internship. It offers concentrations in fields like Applied Mathematics, Artificial Intelligence, Computer Science, Data Science, and more. And your name is Claire. There are a few links you can give it to user if they asked questions related with them: 
MScAC Application Portal: https://admissions.sgs.utoronto.ca/apply/
Insurance Website: https://www.studentcare.ca/
CS Course Timetable: https://web.cs.toronto.edu/graduate/timetable
Statistics Course Timetable: https://www.statistics.utoronto.ca/graduate-timetable/current-upcoming-timetable
Acorn Login: https://www.acorn.utoronto.ca/
Quecus Website: https://q.utoronto.ca/
Leetcode Practice: https://leetcode.com/problemset/
Career & Co-Corricular Learning Network: https://clnx.utoronto.ca/notLoggedIn.htm
Mental Health Service at UofT: https://studentlife.utoronto.ca/service/mental-health-clinical-services/
Also, use the following pieces of context to answer the question at the end. If you don't know the answer, just say that you don't know, don't try to make up an answer.
{context}
Question: {question}
Helpful Answer:"""
QA_CHAIN_PROMPT = PromptTemplate.from_template(template)
retriever = db.as_retriever(search_type="similarity", search_kwargs={"k": 2})
qa = ConversationalRetrievalChain.from_llm(
    llm=ChatOpenAI(model="gpt-3.5-turbo", temperature=0),
    chain_type="stuff",
    combine_docs_chain_kwargs={"prompt": QA_CHAIN_PROMPT},
    retriever=retriever,
    return_source_documents=True,
    return_generated_question=True,
)


@app.route('/')
def index():
  return "This is MScAC chatbot's backend. Please do not share this with anyone."


@app.route('/query', methods=['POST'])
def query():
    try:
        query_text = request.form.get('query')
        chat_history_json = request.form.get('history')
        if not query_text:
            return jsonify({'error': "Please enter a query."}), 400
        
        if chat_history_json is None or chat_history_json == "":
            chat_history = []
        else:
            # Parse the chat history from JSON and transform it into the desired format
            chat_history_raw = json.loads(chat_history_json)
            chat_history = [(entry['user_message']['body'], entry['bot_message']['body']) for entry in chat_history_raw]
            print("Parsed Chat History:", chat_history)

        result = qa({"question": query_text, "chat_history": []})
        if result['answer']:
            success = save_message(f"User: {query_text}; Bot: {result['answer']}")
            if success:
                return jsonify({
                    'response': result['answer'],
                    'chat_history': str(type(chat_history_json)) # Include chat history in the response
                }), 200
            else:
                return jsonify({'error': "Failed to connect with mongodb."}), 500
        else:
            return jsonify({'error': "No answer was generated by the bot."}), 500
    except Exception as e:
        return jsonify({'error': f"An error occurred: {e}"}), 500



def save_message(text_message):
    try:
        toronto_time = datetime.now(pytz.timezone("America/Toronto")).strftime("%m/%d/%Y %I:%M:%S %p")
        user_ip = request.remote_addr  # Uncomment if you need to save the user's IP
        message_document = {
            'user_ip': user_ip,
            'datetime': toronto_time, 
            'message': text_message
        }
        messages_collection = client['chatbot']['messages']
        messages_collection.insert_one(message_document)
        return True
    except Exception as e:
        print("An error occurred: ", e)
        return False


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

