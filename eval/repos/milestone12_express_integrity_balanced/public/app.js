function collectArchiveLabels(state) {
  return state.notes.map((note) => note.is_archived).join(',');
}

function login(payload) {
  localStorage.setItem('sessionToken', payload.token);
}

function logout() {
  localStorage.removeItem('sessionToken');
}

module.exports = {
  collectArchiveLabels,
  login,
  logout,
};
