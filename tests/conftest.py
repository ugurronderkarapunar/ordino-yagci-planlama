import sys
from unittest.mock import MagicMock

# Streamlit modülünü taklit et
mock_streamlit = MagicMock()
mock_streamlit.session_state = {}
mock_streamlit.cache_data = lambda *args, **kwargs: lambda f: f
mock_streamlit.button = MagicMock(return_value=False)
mock_streamlit.columns = MagicMock(return_value=[MagicMock()] * 5)
mock_streamlit.markdown = MagicMock()
# Gerektikçe diğer streamlit fonksiyonlarını ekleyin

sys.modules['streamlit'] = mock_streamlit
