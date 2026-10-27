import { Component, type ComponentType, type ReactNode, lazy } from "react";
import { ErrorState } from "./ui";

const RELOAD_KEY = "wasl.chunk-reload";

function storage(): Storage | null {
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

/** A stale tab can ask for a page chunk that a newer deploy replaced: reload once to pick up the new build. */
export function lazyPage<T extends ComponentType<object>>(load: () => Promise<{ default: T }>) {
  return lazy(() =>
    load()
      .then((m) => {
        storage()?.removeItem(RELOAD_KEY);
        return m;
      })
      .catch((err: unknown) => {
        const s = storage();
        if (s && !s.getItem(RELOAD_KEY)) {
          s.setItem(RELOAD_KEY, "1");
          window.location.reload();
          return new Promise<{ default: T }>(() => {});
        }
        throw err;
      }),
  );
}

/** Never leave a blank screen: show the error with a reload button instead. */
export class ErrorBoundary extends Component<{ children: ReactNode; resetKey?: string }, { error: unknown }> {
  state = { error: null as unknown };

  static getDerivedStateFromError(error: unknown) {
    return { error };
  }

  componentDidUpdate(prev: { resetKey?: string }) {
    if (this.state.error && prev.resetKey !== this.props.resetKey) this.setState({ error: null });
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="mx-auto max-w-xl p-8">
        <ErrorState error={this.state.error} retry={() => window.location.reload()} />
      </div>
    );
  }
}
