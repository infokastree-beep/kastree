"use client";

import { useEffect, useId, useRef, useState } from "react";
import {
  PRODUCTS,
  formatProductLabel,
  type Product,
} from "@/lib/products";

type ProductSwitcherProps = {
  products?: readonly Product[];
  /** Which product is currently active. Defaults to the first entry. */
  activeProductId?: string;
};

export function ProductSwitcher({
  products = PRODUCTS,
  activeProductId = products[0]?.id,
}: ProductSwitcherProps) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const listboxId = useId();

  const activeProduct =
    products.find((product) => product.id === activeProductId) ?? products[0];

  useEffect(() => {
    if (!open) {
      return;
    }

    function handlePointerDown(event: MouseEvent) {
      if (!rootRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setOpen(false);
      }
    }

    document.addEventListener("mousedown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [open]);

  if (!activeProduct) {
    return null;
  }

  function handleSelect(product: Product) {
    if (product.id === activeProduct.id) {
      setOpen(false);
      return;
    }
    // Routing for additional products will plug in here.
    setOpen(false);
  }

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listboxId}
        onClick={() => setOpen((value) => !value)}
        className="flex items-center gap-1.5 rounded border border-stone-200 bg-white px-2.5 py-1.5 text-left text-sm font-semibold tracking-tight text-stone-900 hover:bg-stone-50"
      >
        <span>{formatProductLabel(activeProduct)}</span>
        <svg
          aria-hidden
          viewBox="0 0 20 20"
          fill="currentColor"
          className={`h-4 w-4 shrink-0 text-stone-500 transition-transform ${open ? "rotate-180" : ""}`}
        >
          <path
            fillRule="evenodd"
            d="M5.23 7.21a.75.75 0 011.06.02L10 11.168l3.71-3.938a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z"
            clipRule="evenodd"
          />
        </svg>
      </button>

      {open ? (
        <ul
          id={listboxId}
          role="listbox"
          aria-label="Products"
          className="absolute left-0 top-full z-20 mt-1 min-w-full rounded border border-stone-200 bg-white py-1 shadow-sm"
        >
          {products.map((product) => {
            const isActive = product.id === activeProduct.id;
            return (
              <li key={product.id} role="option" aria-selected={isActive}>
                <button
                  type="button"
                  disabled={isActive}
                  onClick={() => handleSelect(product)}
                  className={`flex w-full items-center justify-between gap-3 px-3 py-2 text-left text-sm ${
                    isActive
                      ? "cursor-default bg-stone-50 font-semibold text-stone-900"
                      : "text-stone-700 hover:bg-stone-50 hover:text-stone-900"
                  }`}
                >
                  <span>{formatProductLabel(product)}</span>
                  {isActive ? (
                    <span className="text-xs font-normal text-stone-500">Active</span>
                  ) : null}
                </button>
              </li>
            );
          })}
        </ul>
      ) : null}
    </div>
  );
}
