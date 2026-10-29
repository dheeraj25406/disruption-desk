from app.core.config import settings
class ConfigurationError(RuntimeError): pass
class ProviderError(RuntimeError): pass

def explanation(case:dict, decision:str, reasons:list[str], alternatives:list[dict])->str:
    if not settings.gemini_api_key: raise ConfigurationError("Gemini API key is missing. Set GEMINI_API_KEY in backend/.env to run AI analysis.")
    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
        from langchain_core.messages import HumanMessage, SystemMessage
        from pydantic import BaseModel
        class Interpretation(BaseModel): explanation:str
        model=ChatGoogleGenerativeAI(model="gemini-3.5-flash-lite",google_api_key=settings.gemini_api_key,temperature=0).with_structured_output(Interpretation)
        answer=model.invoke([SystemMessage(content="Explain the supplied flight disruption and recovery information in two concise, professional sentences for an operations agent. State what happened to the flight or connection and what the next step is. Do not invent facts, options, availability, or change the policy decision. Avoid internal reason codes and technical labels. Do not claim an option is booked or confirmed."),HumanMessage(content=str({"case":case,"policy_decision":decision,"reason_codes":reasons,"alternatives":alternatives}))])
        return answer.explanation
    except ConfigurationError: raise
    except Exception as exc: raise ProviderError(f"Gemini provider/structured-output failure: {type(exc).__name__}") from exc
