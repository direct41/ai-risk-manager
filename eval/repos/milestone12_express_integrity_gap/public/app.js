function collectArchiveLabels(state) {
  return state.notes.map((note) => note.archived).join(',');
}

function login(payload) {
  localStorage.setItem('sessionToken', payload.token);
}

function logout() {
  localStorage.removeItem('session_token');
}

module.exports = {
  collectArchiveLabels,
  login,
  logout,
};
