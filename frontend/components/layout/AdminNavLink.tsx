"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/hooks/useAuth";
import { apiFetch } from "@/lib/api";

type UserMe = {
  role: string;
  is_platform_admin: boolean;
};

export function AdminNavLink() {
  const { getToken, isSignedIn } = useAuth();
  const [show, setShow] = useState(false);

  useEffect(() => {
    if (!isSignedIn) {
      setShow(false);
      return;
    }
    let cancelled = false;
    apiFetch<UserMe>("/users/me", { getToken })
      .then((me) => {
        if (!cancelled) {
          setShow(me.is_platform_admin);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setShow(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [getToken, isSignedIn]);

  if (!show) {
    return null;
  }

  return (
    <Link href="/admin" className="hover:text-stone-900">
      Admin
    </Link>
  );
}
