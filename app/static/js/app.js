/* Upload previews and progress feedback. The API key never enters this script. */
document.querySelectorAll('[data-scan-form]').forEach((form) => {
  const input = form.querySelector('input[type="file"]');
  const zone = form.querySelector('[data-drop-zone]');
  const error = form.querySelector('[data-upload-error]');
  const placeholder = form.querySelector('[data-drop-placeholder]');
  const preview = form.querySelector('[data-preview]');
  const image = form.querySelector('[data-preview-image]');
  const actions = form.querySelector('[data-file-actions]');
  let previewUrl = null;
  image.addEventListener('error', () => { image.hidden = true; });

  function showFile() {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    previewUrl = null;
    error.hidden = true;
    const file = input.files[0];
    if (file && (!/\.(jpe?g|png|webp|gif|bmp|tiff?|avif|heic|heif)$/i.test(file.name) || (file.type && !file.type.startsWith('image/')))) {
      error.textContent = 'Choose a supported photo (JPG, PNG, WebP, GIF, BMP, TIFF, AVIF or HEIC).';
      error.hidden = false;
      input.value = '';
    } else if (file && file.size > 5 * 1024 * 1024) {
      error.textContent = 'This photo is too large. Please choose one under 5 MB.';
      error.hidden = false;
      input.value = '';
    }
    const selected = input.files[0];
    placeholder.hidden = Boolean(selected);
    preview.hidden = !selected;
    actions.hidden = !selected;
    if (selected) {
      image.hidden = false;
      previewUrl = URL.createObjectURL(selected);
      image.src = previewUrl;
      form.querySelector('[data-file-name]').textContent = selected.name;
    } else {
      image.removeAttribute('src');
    }
  }

  input.addEventListener('change', showFile);
  ['dragenter', 'dragover'].forEach((event) => zone.addEventListener(event, () => zone.classList.add('dragging')));
  ['dragleave', 'drop'].forEach((event) => zone.addEventListener(event, () => zone.classList.remove('dragging')));
  zone.addEventListener('drop', (event) => {
    event.preventDefault();
    if (event.dataTransfer.files.length) {
      const selection = new DataTransfer();
      selection.items.add(event.dataTransfer.files[0]);
      input.files = selection.files;
      showFile();
    }
  });
  zone.addEventListener('dragover', (event) => event.preventDefault());
  form.querySelector('[data-remove-file]').addEventListener('click', () => {
    input.value = '';
    showFile();
    input.focus();
  });
  form.addEventListener('submit', () => {
    const button = form.querySelector('[data-submit-button]');
    button.disabled = true;
    form.setAttribute('aria-busy', 'true');
    form.querySelector('[data-button-label]').textContent = 'Finding the right next step…';
    form.querySelector('[data-spinner]').hidden = false;
    form.querySelector('[data-processing-note]').hidden = false;
    form.querySelector('[data-form-footnote]').hidden = true;
  });
  window.addEventListener('pageshow', (event) => { if (event.persisted) window.location.reload(); });
});
