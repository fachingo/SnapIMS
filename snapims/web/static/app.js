(() => {
  const status = document.querySelector('#recognition-status[data-running="true"]');
  if (!status) return;
  const batch = status.dataset.batch;
  const poll = async () => {
    try {
      const response = await fetch(`/review/job/${encodeURIComponent(batch)}`);
      const data = await response.json();
      const strong = status.querySelector('strong');
      if (strong) strong.textContent = data.text;
      if (data.job && data.job.status === 'RUNNING') setTimeout(poll, 450);
      else window.location.reload();
    } catch (_) { setTimeout(poll, 900); }
  };
  setTimeout(poll, 300);
})();
