/**
 * Bloque de resumen genérico: total + desglose por categoría.
 * Reutilizable entre las secciones del Dashboard (pedidos, envíos,
 * vehículos, conductores). No conoce ningún tipo del dominio — solo
 * recibe conteos ya calculados por quien lo usa, así que no hay
 * ningún campo o categoría "inventada" dentro del componente.
 */

export function StatSummary({
  title,
  total,
  breakdown,
}: {
  title: string
  total: number
  breakdown: Record<string, number>
}) {
  return (
    <div className="flex flex-col gap-2 rounded border p-4">
      <h2 className="text-sm font-medium text-muted-foreground">{title}</h2>
      <p className="text-2xl font-medium">{total}</p>
      <dl className="flex flex-col gap-1 text-sm text-muted-foreground">
        {Object.entries(breakdown).map(([key, count]) => (
          <div key={key} className="flex justify-between gap-4">
            <dt>{key}</dt>
            <dd>{count}</dd>
          </div>
        ))}
      </dl>
    </div>
  )
}
