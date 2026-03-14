const state = { page: 2, limit: 10, total: 0 };

async function loadNotes() {
  const payload = await apiFetch('/api/notes?page=' + state.page + '&limit=' + state.limit);
  state.total = payload.total;
}

async function handleCardClick(action) {
  if (action === 'delete') {
    await apiFetch('/api/notes/1', { method: 'DELETE' });
    await loadNotes();
  }
}

function updateSaveButtonState(title, content, refs) {
  refs.saveBtn.disabled = !(title || content);
}

module.exports = {
  loadNotes,
  handleCardClick,
  updateSaveButtonState,
};
