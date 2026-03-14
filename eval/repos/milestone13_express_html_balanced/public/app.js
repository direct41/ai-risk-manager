function renderNotes(state, refs) {
  refs.notesContainer.replaceChildren();
  state.notes.forEach((note) => {
    const article = document.createElement('article');
    const title = document.createElement('h3');
    const body = document.createElement('p');
    title.textContent = note.title;
    body.textContent = note.content;
    article.append(title, body);
    refs.notesContainer.append(article);
  });
}

module.exports = {
  renderNotes,
};
