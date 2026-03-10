function renderNotes(state, refs) {
  refs.notesContainer.innerHTML = state.notes
    .map((note) => `<article><h3>${note.title}</h3><p>${note.content}</p></article>`)
    .join('');
}

module.exports = {
  renderNotes,
};
