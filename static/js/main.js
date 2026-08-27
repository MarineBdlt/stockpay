(() => {
  const priceEl = document.getElementById("display-price");
  if (!priceEl) return;

  const radios = document.querySelectorAll('input[name="storage_gb"]');

  const update = () => {
    const selected = document.querySelector('input[name="storage_gb"]:checked');
    if (!selected) return;
    priceEl.textContent = selected.dataset.price;
    priceEl.parentElement.classList.add("is-updating");
    window.setTimeout(() => {
      priceEl.parentElement.classList.remove("is-updating");
    }, 180);
  };

  radios.forEach((radio) => {
    radio.addEventListener("change", update);
  });
})();
