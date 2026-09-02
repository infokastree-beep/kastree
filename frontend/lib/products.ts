/** Product entries for the dashboard switcher. Add new products here. */

export type Product = {
  /** Stable identifier (e.g. for active-state matching). */
  id: string;
  name: string;
  tagline: string;
  /** Default route when switching to this product. */
  route: string;
};

export const PRODUCTS: readonly Product[] = [
  {
    id: "findraft",
    name: "Kastree",
    tagline: "Financial Intelligence Platform",
    route: "/upload",
  },
] as const;

export function formatProductLabel(product: Product): string {
  return `${product.name} — ${product.tagline}`;
}
