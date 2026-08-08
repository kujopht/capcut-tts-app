"use client";

/**
 * Nap du lieu bat dong bo cho mot trang.
 *
 * VI SAO CAN HOOK NAY: quy tac `react-hooks/set-state-in-effect` cam goi
 * `setState` DONG BO trong than effect. Neu moi trang tu viet
 * `setLoading(true); fetch()...` roi goi trong effect thi deu vi pham.
 *
 * O day than effect chi khoi dong promise; moi `setState` nam trong callback.
 * `reload()` duoc goi tu su kien nguoi dung nen dat trang thai truc tiep duoc.
 */

import { useCallback, useEffect, useState } from "react";
import { errorMessage } from "./session";

interface AsyncState<T> {
  data: T | null;
  loading: boolean;
  error: string;
  /** Loi 404 tach rieng de trang hien "khong tim thay" thay vi loi chung. */
  missing: boolean;
}

export interface AsyncData<T> extends AsyncState<T> {
  reload: () => void;
  setData: (updater: (current: T | null) => T | null) => void;
}

function isNotFound(cause: unknown): boolean {
  return (
    typeof cause === "object" &&
    cause !== null &&
    "status" in cause &&
    (cause as { status: unknown }).status === 404
  );
}

export function useAsyncData<T>(
  fetcher: () => Promise<T>,
  { enabled = true }: { enabled?: boolean } = {},
): AsyncData<T> {
  const [state, setState] = useState<AsyncState<T>>({
    data: null,
    loading: true,
    error: "",
    missing: false,
  });
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;

    fetcher()
      .then((data) => {
        if (!cancelled) setState({ data, loading: false, error: "", missing: false });
      })
      .catch((cause) => {
        if (cancelled) return;
        setState({
          data: null,
          loading: false,
          error: isNotFound(cause) ? "" : errorMessage(cause),
          missing: isNotFound(cause),
        });
      });

    return () => {
      cancelled = true;
    };
  }, [fetcher, enabled, nonce]);

  const reload = useCallback(() => {
    setState((current) => ({ ...current, loading: true, error: "", missing: false }));
    setNonce((value) => value + 1);
  }, []);

  const setData = useCallback((updater: (current: T | null) => T | null) => {
    setState((current) => ({ ...current, data: updater(current.data) }));
  }, []);

  return { ...state, reload, setData };
}
