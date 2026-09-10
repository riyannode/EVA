export const deskPositions: [number, number][] = [[-5.5, -2.7], [0, -2.7], [5.5, -2.7], [-5.5, 2.2], [0, 2.2], [5.5, 2.2]];

export function aislePath(from: [number, number], to: [number, number]): [number, number][] {
  const startLane = from[1] < 0 ? 0 : 5;
  const endLane = to[1] < 0 ? 0 : 5;
  const route: [number, number][] = [[from[0], startLane]];
  if (startLane !== endLane) route.push([2.75, startLane], [2.75, endLane]);
  route.push([to[0], endLane], [to[0], to[1] + 1.03]);
  return route;
}
