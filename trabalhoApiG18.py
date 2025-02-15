# Bibliotecas
from fastapi import FastAPI, status, HTTPException, Depends 
import requests
import json
import xml.etree.ElementTree as ET

import os
from langchain_community.chat_models import ChatOpenAI
import openai
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from typing import List
import re

load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")
MODEL_GPT = "gpt-4o-mini"

# Token de Autenticação
API_TOKEN = os.getenv("API_TOKEN")

URL_API_MEUDANFE = 'https://ws.meudanfe.com/api/v1/get/nfe/xml/'

# Log 
import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s -%(levelname)s - %(message)s')
logger = logging.getLogger("trabG18")

# Reutilização da autenticaçõa para todos os serviços da API
def autenticacao(api_token: str):
    if api_token != API_TOKEN:
        logger.error('O Token informado ' + api_token + " é inválido!")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido")

router = FastAPI(
    title="Trabalho do Grupo 18",
    summary="API desenvolvida para avaliação da disciplina de API do Curso de Pós-Graduação em Sistemas e Agentes Inteligentes da Universidade Federal de Goiás",
    description="Hugo Ginú <br>Pedro Moacir de Carvalho <br>Rafael Peixoto",
    version="1.0.0",
    terms_of_service="https://agentes.inf.ufg.br/",
    license_info={
        "name": "Apache 2.0",
        "url": "https://www.apache.org/licenses/LICENSE-2.0.html",
    },
    dependencies=[Depends(autenticacao)]
)

# Metódo da API para consulta dos dados da NFe 
@router.get("/v1/nfe", summary="Consulta dados completo da NFe")
def consultaNfe(chaveNFe: str):
    logger.info('chaveNFe->' + chaveNFe)
    # Faz a requisição POST com body vazio
    response =  getXmlNFe(chaveNFe)

    # Verifica se a resposta é bem-sucedida
    if response and response.strip:
        return xml_to_json(response)
    else:
        return {"resultado": response.status_code}

# realiza a chamada do serviço de pesquisa da NFe
def getXmlNFe(chaveNFe: str):
     # Faz a requisição POST com body vazio
    response = requests.post(URL_API_MEUDANFE + chaveNFe, data={'empty'})
    #logger.info(response.status_code)
    #logger.info(response.text)

    # Verifica se a resposta é bem-sucedida
    if response.status_code == status.HTTP_200_OK or (response.text and response.text.strip):
        return response.text
    else:
        return response.status_code

# Método para converter uma informação no formato XML para JSON
def xml_to_json(xml_string):
    root = ET.fromstring(xml_string)    
    def parse_element(element):
        data = {}
        tag = element.tag.split('}')[-1]  # Remove namespace
        if element.text and element.text.strip():
            data[tag] = element.text.strip()
        else:
            data[tag] = {child.tag.split('}')[-1]: parse_element(child) for child in element}
        return data[tag]
    return parse_element(root)

@router.get("/v1/nfe/itens", 
             summary="Extrai os Itens da NFe no formato do SPED")
def getItesNFe(chaveNFe: str):
    logger.info('chv_nfe -> ' + chaveNFe)

    xml = getXmlNFe(chaveNFe)

    prompt = """
        Com base arquivo XML contendo uma Nota Fiscal Eletrônica (NF-e) delimitado pelo marcador <arquivo_xml>. 
        Sua tarefa é extrair as informações de cada item da NF-e e retornar uma lista de dicionários com os seguintes campos:
            Seq (nItem)
            Código (cProd)
            Descrição (xProd)
            Quantidade (qCom)
            Valor UN (vUnCom)
            Valor Total (vProd)
        O XML segue o esquema da NF-e e os itens estão dentro da tag <det>. 
        Utilize parsing XML para encontrar os valores corretos. 
        Certifique-se de ignorar namespaces, se houver, e validar se os campos extraídos estão presentes no XML.
        Retorne a saída no seguinte formato: Seq|Código|Descrição|Quantidade|Valor UN|Valor Total        
        A saída deve ser somente as informações extraídas <arquivo_xml> informado e nada mais. 
        Não quero código de exemplo, quero as informações extraídas e somente isso.
        <arquivo_xml>
    """ + xml + "</arquivo_xml>"
    
    # Configurar o modelo (você pode trocar 'gpt-4' se tiver acesso)
    llm = ChatOpenAI(temperature=0, model=MODEL_GPT)

	# Enviar o prompt diretamente para o modelo
    resposta = llm.invoke(prompt)
    resposta = resposta.replace('```plaintext', '')
    resposta = resposta.replace('```', '')
    logger.info('resposta ->' + resposta)

    return resposta

# Metódo da API para vinculação dos itens do SPED com os itens do XML 
class ItemNotaFiscal(BaseModel):
    seq: int = Field(description="Sequencial do item")
    cod_item: str = Field(description="Código do produto")
    desc_item: str = Field(description="Descrição do Item")
    qt_item: float = Field(description="Quantidade")
    valor_un: float = Field(description="Valor unitário")
    valor_total: float = Field(description="Valor Total do Item")

class Vinculacao(BaseModel):
    lista_01_seq: int = Field(description="Sequencial do item no EFD")
    lista_02_seq: int = Field(description="Sequencial do item no XML")
    regra_vinculo: str = Field(description="Forma como foi vinculado o item da lista 01 com o item da lista 02 (Regra 00 | Regra 01 | Regra 02 | Regra 03)")
    
class VinculacaoReq(BaseModel):
    chv_nfe: str = Field(description="Chave da nota fiscal")
    itens_efd: List[ItemNotaFiscal] = Field(description="Lista de itens do SPED")
    #itens_xml: List[ItemNotaFiscal] = Field(description="Lista de itens da Lista de Itens do XML")

class VinculacaoRet(BaseModel):
    chv_nfe: str = Field(description="Chave da nota fiscal")
    itens_vinculados: List[Vinculacao] = Field(description="Lista de itens com a vinculação entre SPED e XML")


@router.post("/v1/vinculacao", 
             response_model=VinculacaoRet,
             summary="Vincula Itens da Nota Fiscal do SPED com os itens do XML da NFe")
def analisar_vinculacao(req: VinculacaoReq):
    logger.info('chv_nfe -> ' + req.chv_nfe)
    itens_efd = CABECALHO + '\n' + formatar_itens(req.itens_efd)
    #itens_xml = CABECALHO + formatar_itens(req.itens_xml)
    itens_xml = CABECALHO + getItesNFe(req.chv_nfe)
    logger.info('itens_efd -> ' + itens_efd)
    # logger.info('itens_xml -> ' + itens_xml)
    #logger.info(f'itens_efd -> {json.dumps([item.model_dump() for item in req.itens_efd], indent=2)}')
    #logger.info(f'itens_xml -> {json.dumps([item.model_dump() for item in req.itens_xml], indent=2)}')

    prompt = PROMPT_VINCULACAO
    prompt = prompt.replace('[itens_efd]', itens_efd)
    prompt = prompt.replace('[itens_xml]', itens_xml)
    # logger.info('Prompt: \n' + prompt )
    
    # Configurar o modelo (você pode trocar 'gpt-4' se tiver acesso)
    llm = ChatOpenAI(temperature=0, model=MODEL_GPT)

	# Enviar o prompt diretamente para o modelo
    resposta = llm.invoke(prompt)
    #logger.info('resposta ->' + resposta)
    #logger.info('resposta ->\n' + extrair_json(resposta))
    
    json_str = extrair_json(resposta);
    
    dados = json.loads(json_str)  # Converte para dicionário
    itens_vinculados = [Vinculacao(**item) for item in dados["vinculacao"]]  # Mapeia para objetos

    ret = VinculacaoRet
    ret.chv_nfe = req.chv_nfe
    ret.itens_vinculados = itens_vinculados

    return ret

# Formata as informações para o prompt
def formatar_itens(itens: List[ItemNotaFiscal]) -> str:
    return "\n".join(f"{item.seq}|{item.cod_item}|{item.desc_item}|{item.qt_item}|{item.valor_un}|{item.valor_total}" for item in itens)

# Remover textos retornados pela LLM fora do JSON
def extrair_json(texto: str) -> str:
    match = re.search(r'\{.*\}', texto, re.DOTALL)  # Captura tudo entre { e }
    return match.group(0) if match else ""  # Retorna apenas o conteúdo encontrado

# Prompt de vinculação dos itens
CABECALHO = """Seq|Código do Item|Descrição|Quantidade|Valor UN|Valor Total"""
PROMPT_VINCULACAO = """
	Realize a vinculação dos itens da lista 01: <dadosEfd>[itens_efd]</dadosEfd> 
    com os da lista 02: <dadosXml>[itens_xml]</dadosXml>. 
    As informações na lista 01 e 02 estão separadas por pipe |, sendo a primeira linha o cabeçalho descritivo do que é cada informação.
    Para vinculação considere as seguintes regras: 
    <regra 01>
        Faça a vinculação pela similaridade considerando apenas o campo 'Descrição' da lista 01 com a lista 02.
        Não pode existir outra ocorrência com a mesma similaridade.
    </regra 01>
    <regra 02>
        Faça a vinculação pela aproximação do 'Valor Total', considerando o percentual da diferença entre o valor da lista 01 com o valor da lista 02.
        Para calcular o percentual, siga as instruções do <exemplo>
        <exemplo>Subtraia o valor total do item 2 do valor total do item 1 (100 - 99), desconsidere o sinal de negativo, 
        e divida o resultado pelo valor total do item 1 (1 / 100 = 0,01) e multiplique por 100 (0,01 x 100 = 1). 
        </exemplo>
        Se resultado for menor que 2 (2%) faça a vincuação, desde que não tenha outro item com uma aproximação menor ou igual.
    </regra 02>
    <regra 03>
        Passo 1: Verifique se a lista 01 possui a mesma quantidade de itens da lista 02. Caso as listas tenham quantidade diferentes,
        selecione a lista que possui mais itens e faça o seguinte:
            - Para fins de calculo na etapa 2, some o valor total dos itens que possuirem a mesma descrição, e considere esse valor para o passo 2,
            por exemplo, o item 01 possui um valor de 100 e o item 02 um valor de 50, para o passo 2, considere para esses dois itens o valor de 150. 
       Passo 2: Aplique a regra 02 desconsideração a margem de aproximação de 5%, vinculando os itens pelo valor mais aproximado. Para desempate aplique a regra 01.     
    </regra 03>
    Para realizar a vinculação execute as seguintes etapas:
    <etapa 1>
        Para cada item da lista 01 aplique a regra 01 para todos os itens da lista 02 que ainda não tenham sido vinculados.
        Ao realizar a vinculação, retire da lista 01 e da lista 02 o item que vinculado.
        Caso a lista 01 ou lista 02 tenha apenas um item sem resolução, realize a vinculação desses itens e considere como resolução a Regra 00.
    </etapa 1>
    <etapa 2>
        Para cada item da lista 01 que não tenha sido resolvido na regra 01, aplique a regra 02 para todos os itens da lista 02 que ainda não tenham sido vinculados.
        Ao realizar a vinculação, retire da lista 01 e da lista 02 o item que foi vinculado.
        Caso a lista 01 ou lista 02 tenha apenas um item resolução, realize a vinculação desses itens e considere como resolução a Regra 00.
    </etapa 2>
    <etapa 3>
        Para cada item da lista 01 que não tenha sido resolvido nas etapas anteriores, aplique a regra 03 para todos os itens da lista 02 que ainda não tenham sido vinculados.
        Ao realizar a vinculação, retire da lista 01 e da lista 02 o item que vinculado.
        Caso a lista 01 ou lista 02 tenha apenas um item resolução, realize a vinculação desses itens e considere como resolução a Regra 00.
    </etapa 3>
    <etapa 4>
        Execute a etapa 3 até que todos os itens da lista 1 e da lista 2 tenham vinculação. 
    </etapa 4>

    Finalizada as vinculações, gere a resposta em JSON com os atributos conforme exemplo
    <exemplo>
        {
            "vinculacao": [
                {
                    "lista_01_seq": 1,
                    "lista_02_seq": 2,
                    "regra_vinculo": "Regra 01"
                },
                {
                    "lista_01_seq": 2,
                    "lista_02_seq": 1,
                    "regra_vinculo": "Regra 00"
                }
            ]
        }
    </exemplo>
    A resposta deve contar apenas o JSON  e nada mais.
"""