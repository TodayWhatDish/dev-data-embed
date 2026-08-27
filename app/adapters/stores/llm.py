# Last Updated : 2026-08-27

"""모델에 말을 거는 자리로 클라이언트 두 개를르 만들어 두는 것이 전부다.
   
   로컬과 상용의 분기는 base_url 하나다.
   프롬프트 자체를 조립하는 일은 domain/prompting 이 진행하며, 무엇을 어떤 순서로 시키는지는 app/features 쪽이 담당한다.
"""

from langchain_openai import ChatOpenAI

# from app.core.config import 
# from app.core.trace