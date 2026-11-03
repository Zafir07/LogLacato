# Frontend (Etapa 6)

React + TypeScript + Vite + Tailwind CSS + Recharts + React Router + Lucide.

| Pasta | Conteúdo |
|-------|----------|
| `src/layouts/` | estrutura das telas: sidebar, cabeçalho com o usuário, área de conteúdo |
| `src/pages/` | Dashboard, Tempo real, Viagens, Veículos, Alertas, Relatórios, Coleta, Login |
| `src/components/` | cards de indicador, tabelas paginadas, filtros, badges de estado |
| `src/charts/` | gráficos Recharts (temperatura, pH, acidez, volume, comparação) |
| `src/services/` | cliente da API REST e da conexão WebSocket |
| `src/hooks/` | estado compartilhado: autenticação, tempo real, filtros |
| `src/types/` | tipos TypeScript espelhando os esquemas da API |

Regra de interface: um valor só aparece como "ao vivo" se a leitura for recente.
Leitura antiga aparece com a idade ("há 12 min") e o aviso de que pode não representar
a condição atual do leite.
