import { createTheme, ThemeProvider as MuiThemeProvider } from "@mui/material/styles";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Chip from "@mui/material/Chip";
import LinearProgress from "@mui/material/LinearProgress";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { useMemo } from "react";
import { useSiteTheme } from "@/lib/theme";

const metrics = [
  { label: "Public API modules", value: "24", progress: 92 },
  { label: "Diagram recipes", value: "6", progress: 70 },
  { label: "Skill reference docs", value: "16", progress: 84 },
  { label: "Python versions", value: "3.9–3.13", progress: 100 },
];

/**
 * MUI showcase strip on the home page. The MUI theme palette follows the
 * site-wide light/dark toggle so both component systems stay in sync.
 */
export default function MuiShowcase() {
  const theme = useSiteTheme() ?? "light";

  const muiTheme = useMemo(
    () =>
      createTheme({
        palette: {
          mode: theme,
          primary: { main: theme === "dark" ? "#60a5fa" : "#2563eb" },
        },
        typography: { fontFamily: "'Inter Variable', system-ui, sans-serif" },
      }),
    [theme],
  );

  return (
    <MuiThemeProvider theme={muiTheme}>
      <Stack direction={{ xs: "column", sm: "row" }} spacing={2} sx={{ width: "100%" }}>
        {metrics.map((metric) => (
          <Card key={metric.label} variant="outlined" sx={{ flex: 1, bgcolor: "background.paper" }}>
            <CardContent>
              <Typography variant="h5" component="p" sx={{ fontWeight: 700 }}>
                {metric.value}
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
                {metric.label}
              </Typography>
              <LinearProgress
                variant="determinate"
                value={metric.progress}
                aria-label={`${metric.label} indicator`}
              />
              <Stack direction="row" spacing={1} sx={{ mt: 1.5 }}>
                <Chip label="included" size="small" color="primary" variant="outlined" />
              </Stack>
            </CardContent>
          </Card>
        ))}
      </Stack>
    </MuiThemeProvider>
  );
}
