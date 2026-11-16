<script>
  let { label = 'Apply', disabled = false, pending = false, onclick = () => {}, testid = null } = $props();

  function activate(event) {
    if (disabled || pending) return;
    onclick(event);
  }
</script>

<button type="button" class="primary" data-testid={testid ?? 'apply'} disabled={disabled || pending} aria-busy={pending} onclick={activate}>
  {label}
</button>
