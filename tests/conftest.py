import sys
from unittest.mock import MagicMock

mock_st = MagicMock()
mock_st.session_state = {}
mock_st.cache_data = lambda *a, **kw: lambda f: f
mock_st.button = MagicMock(return_value=False)
mock_st.columns = MagicMock(return_value=[MagicMock()]*5)
mock_st.markdown = MagicMock()
mock_st.expander = MagicMock()
mock_st.tabs = MagicMock(return_value=[MagicMock()]*10)
mock_st.selectbox = MagicMock(return_value="")
mock_st.text_input = MagicMock(return_value="")
mock_st.number_input = MagicMock(return_value=0)
mock_st.date_input = MagicMock(return_value=None)
mock_st.form_submit_button = MagicMock(return_value=False)
mock_st.caption = MagicMock()
mock_st.sidebar = MagicMock()
mock_st.set_page_config = MagicMock()

sys.modules["streamlit"] = mock_st
