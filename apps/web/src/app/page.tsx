"use client";

import { useCallback, useEffect, useState } from "react";
import {
  ApiUnreachableError,
  API_BASE_URL,
  getLiveness,
  getReadiness,
  getServiceStatus,
  type ReadinessResponse,
  type ServiceStatusResponse,
} from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";

interface SystemStatusState {
  loading: boolean;
  fetchedAt: Date | null;
  liveness: string | null;
  readiness: ReadinessResponse | null;
  service: ServiceStatusResponse | null;
  error: string | null;
}

const INITIAL_STATE: SystemStatusState = {
  loading: true,
  fetchedAt: null,
  liveness: null,
  readiness: null,
  service: null,
  error: null,
};

export default function SystemStatusPage() {
  const [state, setState] = useState<SystemStatusState>(INITIAL_STATE);

  const [refreshToken, setRefreshToken] = useState(0);
  const refresh = useCallback(() => setRefreshToken((prev) => prev + 1), []);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setState((prev) => ({ ...prev, loading: true, error: null }));
      try {
        const [liveness, readiness, service] = await Promise.all([
          getLiveness(),
          getReadiness(),
          getServiceStatus(),
        ]);
        if (cancelled) return;
        setState({
          loading: false,
          fetchedAt: new Date(),
          liveness: liveness.body.status,
          readiness: readiness.body,
          service: service.body,
          error: null,
        });
      } catch (cause) {
        if (cancelled) return;
        const message =
          cause instanceof ApiUnreachableError
            ? `Could not reach the AURA API at ${API_BASE_URL}. Is services/api running?`
            : "Unexpected error while checking system status.";
        setState({ ...INITIAL_STATE, loading: false, error: message });
      }
    }

    void load();

    return () => {
      cancelled = true;
    };
  }, [refreshToken]);

  return (
    <main className="mx-auto flex w-full max-w-2xl flex-1 flex-col gap-6 px-6 py-12">
      <header>
        <h1 className="text-2xl font-semibold">AURA System Status</h1>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          Infrastructure foundation status for the AURA backend. This page
          reports only real, live checks against services/api - it does not
          show transportation, prediction, or fleet data (none exists yet;
          see docs/architecture/12-development-phases.md).
        </p>
      </header>

      <section className="flex items-center justify-between rounded-lg border border-gray-200 p-4 dark:border-gray-800">
        <div>
          <p className="text-sm font-medium">API reachable at</p>
          <p className="font-mono text-sm text-gray-500 dark:text-gray-400">{API_BASE_URL}</p>
        </div>
        <button
          type="button"
          onClick={refresh}
          disabled={state.loading}
          className="rounded-md border border-gray-300 px-3 py-1.5 text-sm font-medium hover:bg-gray-50 disabled:opacity-50 dark:border-gray-700 dark:hover:bg-gray-800"
        >
          {state.loading ? "Checking..." : "Recheck"}
        </button>
      </section>

      {state.error ? (
        <section className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800 dark:border-red-900 dark:bg-red-950/40 dark:text-red-300">
          {state.error}
        </section>
      ) : (
        <section className="divide-y divide-gray-200 rounded-lg border border-gray-200 dark:divide-gray-800 dark:border-gray-800">
          <Row label="Liveness (/healthz)" status={state.liveness ?? undefined} />
          <Row label="Database" status={state.readiness?.checks.database} />
          <Row label="Redis" status={state.readiness?.checks.redis} />
          <Row label="Overall readiness" status={state.readiness?.status} />
        </section>
      )}

      {state.service && (
        <section className="rounded-lg border border-gray-200 p-4 text-sm dark:border-gray-800">
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1">
            <dt className="text-gray-500 dark:text-gray-400">Service</dt>
            <dd>{state.service.name}</dd>
            <dt className="text-gray-500 dark:text-gray-400">Version</dt>
            <dd>{state.service.version}</dd>
            <dt className="text-gray-500 dark:text-gray-400">Environment</dt>
            <dd>{state.service.environment}</dd>
          </dl>
        </section>
      )}

      <footer className="text-xs text-gray-400 dark:text-gray-600">
        {state.fetchedAt ? `Last checked ${state.fetchedAt.toLocaleTimeString()}` : " "}
      </footer>
    </main>
  );
}

function Row({ label, status }: { label: string; status: string | undefined }) {
  return (
    <div className="flex items-center justify-between px-4 py-3">
      <span className="text-sm">{label}</span>
      <StatusBadge status={status} />
    </div>
  );
}
