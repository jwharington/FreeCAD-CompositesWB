#version 130
precision mediump float;

uniform float darken = 0.5;
uniform float x_scale = 16.0;
uniform float y_scale = 8.0;
uniform float z_scale = 2.0;


// https://github.com/rreusser/glsl-solid-wireframe?tab=readme-ov-file

float gridFactor (float parameter, float width, float feather) {
  float w1 = width - feather * 0.5;
  float d = fwidth(parameter);
  float looped = 0.5 - abs(mod(parameter, 1.0) - 0.5);
  return smoothstep(d * w1, d * (w1 + feather), looped);
}

float gridFactor (float parameter, float width) {
  float d = fwidth(parameter);
  float looped = 0.5 - abs(mod(parameter, 1.0) - 0.5);
  return smoothstep(d * (width - 0.5), d * (width + 0.5), looped);
}


float gridFactor (vec2 parameter, float width, float feather) {
  float w1 = width - feather * 0.5;
  vec2 d = fwidth(parameter);
  vec2 looped = 0.5 - abs(mod(parameter, 1.0) - 0.5);
  vec2 a2 = smoothstep(d * w1, d * (w1 + feather), looped);
  return min(a2.x, a2.y);
}


float gridFactor (vec2 parameter, float width) {
  vec2 d = fwidth(parameter);
  vec2 looped = 0.5 - abs(mod(parameter, 1.0) - 0.5);
  vec2 a2 = smoothstep(d * (width - 0.5), d * (width + 0.5), looped);
  return min(a2.x, a2.y);
}


float gridFactor (vec3 parameter, float width, float feather) {
  float w1 = width - feather * 0.5;
  vec3 d = fwidth(parameter);
  vec3 looped = 0.5 - abs(mod(parameter, 1.0) - 0.5);
  vec3 a2 = smoothstep(d * w1, d * (w1 + feather), looped);
  return min(a2.x, a2.y);
}


float gridFactor (vec3 parameter, float width) {
  vec3 d = fwidth(parameter);
  vec3 looped = 0.5 - abs(mod(parameter, 1.0) - 0.5);
  vec3 a2 = smoothstep(d * (width - 0.5), d * (width + 0.5), looped);
  return min(a2.x, a2.y);
}


float mixcol(float col, float amount) {
  return col*(1.0-darken*amount);
}

void main() {
  float pixel_width = 1.0;
  float feather = 0.0;
  vec3 coord = vec3(x_scale * gl_TexCoord[0].s,
                    y_scale * gl_TexCoord[0].t,
                    z_scale * gl_TexCoord[0].r);
  vec3 grid = vec3(gridFactor(coord.x, pixel_width, feather),
                   gridFactor(coord.y, pixel_width, feather),
                   gridFactor(coord.z, pixel_width, feather));
  gl_FragColor = vec4(mixcol(gl_Color.r, grid.x),
                      mixcol(gl_Color.g, grid.y),
                      mixcol(gl_Color.b, grid.z),
                      gl_Color.a);
}
