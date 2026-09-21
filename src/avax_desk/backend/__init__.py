"""الواجهة الخلفية — قاعدة البيانات ودفع الدورات."""

from .supabase_client import SupabaseBackend, load_dotenv

__all__ = ["SupabaseBackend", "load_dotenv"]
