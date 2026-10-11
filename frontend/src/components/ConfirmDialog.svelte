<script>
  let {
    open = false,
    title = '',
    body = '',
    confirmLabel = 'Confirm',
    cancelLabel = 'Cancel',
    onconfirm = () => {},
    oncancel = () => {},
  } = $props();

  function onkeydown(event) {
    if (event.key === 'Escape') oncancel();
  }
</script>

{#if open}
  <div
    role="dialog"
    aria-modal="true"
    aria-labelledby="confirm-title"
    tabindex="-1"
    data-testid="confirm-dialog"
    onkeydown={onkeydown}
  >
    <h2 id="confirm-title">{title}</h2>
    <p>{body}</p>
    <button type="button" onclick={oncancel}>{cancelLabel}</button>
    <button type="button" onclick={onconfirm}>{confirmLabel}</button>
  </div>
{/if}
