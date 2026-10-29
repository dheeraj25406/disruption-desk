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
        answer=model.invoke([SystemMessage(content=(
            "Explain the supplied recovery assessment in two concise, professional sentences. "
            "Source boundaries are strict: the case, customer, affected flight, disruption, and itinerary are simulated training data. "
            "The policy_decision, reason_codes, and connection_assessments come from the deterministic policy engine. "
            "AirLabs is a source only for individual schedule records present in alternatives. "
            "If alternatives is empty, say that no exact-date provider schedule records were returned; do not imply AirLabs determined the policy decision or connection risk. "
            "Explain the provided timing and policy outcome, then state the operator's next step. "
            "Never invent flights, timings, facts, or options; infer no seat, fare, or booking availability; and do not change or override policy. "
            "Avoid internal reason codes. Never claim an option is booked or confirmed."
        )),HumanMessage(content=str({"case":case,"policy_decision":decision,"reason_codes":reasons,"policy_source":"deterministic policy engine","alternatives":alternatives,"provider_records_returned":len(alternatives)}))])
        return answer.explanation
    except ConfigurationError: raise
    except Exception as exc: raise ProviderError(f"Gemini provider/structured-output failure: {type(exc).__name__}") from exc
