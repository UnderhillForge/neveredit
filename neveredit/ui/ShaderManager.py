"""Shader management for OpenGL rendering."""
import copy
import logging

from OpenGL.GL import *
from neveredit.util import Utils

logger = logging.getLogger("neveredit.shader")
Numeric = Utils.getNumPy()
LinearAlgebra = Utils.getLinAlg()


def _color_param(label, default):
    return {
        'type': 'color',
        'label': label,
        'default': list(default),
    }


def _float_param(label, default, minimum, maximum, step, uniform=None):
    definition = {
        'type': 'float',
        'label': label,
        'default': float(default),
        'min': float(minimum),
        'max': float(maximum),
        'step': float(step),
    }
    if uniform:
        definition['uniform'] = uniform
    return definition


def _int_param(label, default, minimum, maximum, uniform=None):
    definition = {
        'type': 'int',
        'label': label,
        'default': int(default),
        'min': int(minimum),
        'max': int(maximum),
        'step': 1,
    }
    if uniform:
        definition['uniform'] = uniform
    return definition


SHADERS = {
    'None': {
        'name': 'No Shader',
        'description': 'Standard rendering without a custom shader program.',
        'vertex': None,
        'fragment': None,
        'parameters': {},
    },
    'Skeleton': {
        'name': 'Skeleton',
        'description': 'Flat lit preview with configurable tint and posterization.',
        'vertex': '''
#version 120
varying vec3 vNormal;
varying vec2 vTexCoord;
uniform mat4 uProjectionMatrix;
uniform mat4 uModelViewMatrix;
uniform mat3 uNormalMatrix;

void main() {
    vNormal = normalize(uNormalMatrix * gl_Normal);
    vTexCoord = gl_MultiTexCoord0.st;
    gl_Position = uProjectionMatrix * uModelViewMatrix * gl_Vertex;
}
        ''',
        'fragment': '''
#version 120
varying vec3 vNormal;
varying vec2 vTexCoord;
uniform vec3 uTintColor;
uniform float uBrightness;
uniform int uColorDepth;
uniform sampler2D uTexture;
uniform float uTextureBlend;

void main() {
    float rim = 1.0 - max(dot(normalize(vNormal), vec3(0.0, 0.0, 1.0)), 0.0);
    vec3 color = uTintColor * (0.45 + rim * uBrightness);
    float levels = max(float(uColorDepth), 2.0);
    color = floor(clamp(color, 0.0, 1.0) * levels) / levels;
    vec3 texColor = texture2D(uTexture, vTexCoord).rgb;
    gl_FragColor = vec4(mix(color, color * texColor, uTextureBlend), 1.0);
}
        ''',
        'parameters': {
            'tint_color': dict(_color_param('Tint', (0.82, 0.42, 0.42)), uniform='uTintColor'),
            'brightness': _float_param('Brightness', 1.0, 0.2, 2.5, 0.05, uniform='uBrightness'),
            'color_depth': _int_param('Color depth', 6, 2, 24, uniform='uColorDepth'),
            'texture_blend': _float_param('Texture blend', 0.0, 0.0, 1.0, 0.05, uniform='uTextureBlend'),
        },
    },
    'Wireframe': {
        'name': 'Wireframe',
        'description': 'True wireframe mode with configurable line width and tint.',
        'vertex': '''
#version 120
uniform mat4 uProjectionMatrix;
uniform mat4 uModelViewMatrix;

void main() {
    gl_Position = uProjectionMatrix * uModelViewMatrix * gl_Vertex;
}
        ''',
        'fragment': '''
#version 120
uniform vec3 uLineColor;
uniform float uBrightness;

void main() {
    gl_FragColor = vec4(clamp(uLineColor * uBrightness, 0.0, 1.0), 1.0);
}
        ''',
        'parameters': {
            'line_color': dict(_color_param('Line color', (0.1, 0.92, 0.95)), uniform='uLineColor'),
            'brightness': _float_param('Brightness', 1.0, 0.2, 2.5, 0.05, uniform='uBrightness'),
            'line_width': _float_param('Line width', 1.5, 1.0, 6.0, 0.25),
        },
        'render_state': {
            'polygon_mode': 'line',
            'line_width_param': 'line_width',
        },
    },
    'Gouraud': {
        'name': 'Gouraud',
        'description': 'Per-vertex lighting with adjustable material response and posterization.',
        'vertex': '''
#version 120
varying vec3 vColor;
varying vec2 vTexCoord;
uniform mat4 uProjectionMatrix;
uniform mat4 uModelViewMatrix;
uniform mat3 uNormalMatrix;
uniform vec3 uBaseColor;
uniform float uAmbientStrength;
uniform float uDiffuseStrength;
uniform float uSpecularStrength;
uniform float uShininess;
uniform int uColorDepth;
uniform vec4 uSceneAmbient;
uniform vec4 uSceneDiffuse;
uniform vec4 uSceneSpecular;
uniform vec4 uLightPosition;
uniform vec3 uMaterialAmbient;
uniform vec3 uMaterialDiffuse;
uniform vec3 uMaterialSpecular;
uniform float uMaterialShininess;

void main() {
    vec3 normal = normalize(uNormalMatrix * gl_Normal);
    vec3 viewPos = (uModelViewMatrix * gl_Vertex).xyz;
    vec3 lightDir = normalize(uLightPosition.xyz - viewPos);
    vec3 viewDir = normalize(-viewPos);
    vec3 halfDir = normalize(lightDir + viewDir);

    float diffuseFactor = max(dot(normal, lightDir), 0.0);
    float matShininess = max(uMaterialShininess * (uShininess / 32.0), 1.0);

    vec3 ambient = uSceneAmbient.rgb * uMaterialAmbient * uAmbientStrength;
    vec3 diffuse = uSceneDiffuse.rgb * uMaterialDiffuse * diffuseFactor * uDiffuseStrength;
    float specularFactor = 0.0;
    if (diffuseFactor > 0.0) {
        specularFactor = pow(max(dot(normal, halfDir), 0.0), matShininess);
    }
    vec3 specular = uSceneSpecular.rgb * uMaterialSpecular * specularFactor * uSpecularStrength;

    vec3 color = uBaseColor * (ambient + diffuse) + specular;
    float levels = max(float(uColorDepth), 2.0);
    vColor = floor(clamp(color, 0.0, 1.0) * levels) / levels;
    vTexCoord = gl_MultiTexCoord0.st;
    gl_Position = uProjectionMatrix * uModelViewMatrix * gl_Vertex;
}
        ''',
        'fragment': '''
#version 120
varying vec3 vColor;
varying vec2 vTexCoord;
uniform sampler2D uTexture;
uniform float uTextureBlend;

void main() {
    vec3 texColor = texture2D(uTexture, vTexCoord).rgb;
    gl_FragColor = vec4(mix(vColor, vColor * texColor, uTextureBlend), 1.0);
}
        ''',
        'parameters': {
            'base_color': dict(_color_param('Base color', (0.95, 0.9, 0.84)), uniform='uBaseColor'),
            'ambient_strength': _float_param('Ambient', 0.28, 0.0, 1.5, 0.02, uniform='uAmbientStrength'),
            'diffuse_strength': _float_param('Diffuse', 0.72, 0.0, 2.0, 0.02, uniform='uDiffuseStrength'),
            'specular_strength': _float_param('Specular', 0.24, 0.0, 2.0, 0.02, uniform='uSpecularStrength'),
            'shininess': _float_param('Shininess', 24.0, 1.0, 96.0, 1.0, uniform='uShininess'),
            'color_depth': _int_param('Color depth', 12, 2, 32, uniform='uColorDepth'),
            'texture_blend': _float_param('Texture blend', 0.0, 0.0, 1.0, 0.05, uniform='uTextureBlend'),
        },
    },
    'Phong': {
        'name': 'Blinn-Phong',
        'description': 'Per-fragment lighting with adjustable color depth, highlight size, and intensity.',
        'vertex': '''
#version 120
varying vec3 vNormal;
varying vec3 vPosition;
varying vec2 vTexCoord;
uniform mat4 uProjectionMatrix;
uniform mat4 uModelViewMatrix;
uniform mat3 uNormalMatrix;

void main() {
    vNormal = normalize(uNormalMatrix * gl_Normal);
    vPosition = (uModelViewMatrix * gl_Vertex).xyz;
    vTexCoord = gl_MultiTexCoord0.st;
    gl_Position = uProjectionMatrix * uModelViewMatrix * gl_Vertex;
}
        ''',
        'fragment': '''
#version 120
varying vec3 vNormal;
varying vec3 vPosition;
varying vec2 vTexCoord;
uniform vec3 uBaseColor;
uniform float uAmbientStrength;
uniform float uDiffuseStrength;
uniform float uSpecularStrength;
uniform float uShininess;
uniform int uColorDepth;
uniform sampler2D uTexture;
uniform float uTextureBlend;
uniform vec4 uSceneAmbient;
uniform vec4 uSceneDiffuse;
uniform vec4 uSceneSpecular;
uniform vec4 uLightPosition;
uniform vec3 uMaterialAmbient;
uniform vec3 uMaterialDiffuse;
uniform vec3 uMaterialSpecular;
uniform float uMaterialShininess;

void main() {
    vec3 normal = normalize(vNormal);
    vec3 lightDir = normalize(uLightPosition.xyz - vPosition);
    vec3 viewDir = normalize(-vPosition);
    vec3 halfDir = normalize(lightDir + viewDir);

    float diffuseFactor = max(dot(normal, lightDir), 0.0);
    float matShininess = max(uMaterialShininess * (uShininess / 32.0), 1.0);
    float specularFactor = 0.0;
    if (diffuseFactor > 0.0) {
        specularFactor = pow(max(dot(normal, halfDir), 0.0), matShininess);
    }

    vec3 ambient = uSceneAmbient.rgb * uMaterialAmbient * uAmbientStrength;
    vec3 diffuse = uSceneDiffuse.rgb * uMaterialDiffuse * diffuseFactor * uDiffuseStrength;
    vec3 specular = uSceneSpecular.rgb * uMaterialSpecular * specularFactor * uSpecularStrength;

    vec3 color = uBaseColor * (ambient + diffuse) + specular;
    float levels = max(float(uColorDepth), 2.0);
    color = floor(clamp(color, 0.0, 1.0) * levels) / levels;
    vec3 texColor = texture2D(uTexture, vTexCoord).rgb;
    gl_FragColor = vec4(mix(color, color * texColor, uTextureBlend), 1.0);
}
        ''',
        'parameters': {
            'base_color': dict(_color_param('Base color', (1.0, 0.92, 0.86)), uniform='uBaseColor'),
            'ambient_strength': _float_param('Ambient', 0.2, 0.0, 1.5, 0.02, uniform='uAmbientStrength'),
            'diffuse_strength': _float_param('Diffuse', 0.72, 0.0, 2.0, 0.02, uniform='uDiffuseStrength'),
            'specular_strength': _float_param('Specular', 0.45, 0.0, 2.0, 0.02, uniform='uSpecularStrength'),
            'shininess': _float_param('Highlight size', 32.0, 1.0, 128.0, 1.0, uniform='uShininess'),
            'color_depth': _int_param('Color depth', 14, 2, 32, uniform='uColorDepth'),
            'texture_blend': _float_param('Texture blend', 0.0, 0.0, 1.0, 0.05, uniform='uTextureBlend'),
        },
    },
    'Cel': {
        'name': 'Cel (Toon)',
        'description': 'Toon shading with controllable band count and colors.',
        'vertex': '''
#version 120
varying vec3 vNormal;
varying vec3 vPosition;
varying vec2 vTexCoord;
uniform mat4 uProjectionMatrix;
uniform mat4 uModelViewMatrix;
uniform mat3 uNormalMatrix;

void main() {
    vNormal = normalize(uNormalMatrix * gl_Normal);
    vPosition = (uModelViewMatrix * gl_Vertex).xyz;
    vTexCoord = gl_MultiTexCoord0.st;
    gl_Position = uProjectionMatrix * uModelViewMatrix * gl_Vertex;
}
        ''',
        'fragment': '''
#version 120
varying vec3 vNormal;
varying vec3 vPosition;
varying vec2 vTexCoord;
uniform vec3 uShadowColor;
uniform vec3 uMidColor;
uniform vec3 uHighlightColor;
uniform int uLevels;
uniform sampler2D uTexture;
uniform float uTextureBlend;

void main() {
    vec3 normal = normalize(vNormal);
    vec3 lightDir = normalize(vec3(1.0, 1.0, 1.0) - vPosition);
    float intensity = clamp(dot(normal, lightDir), 0.0, 1.0);
    float levels = max(float(uLevels), 2.0);
    float quantized = floor(intensity * levels) / (levels - 1.0);

    vec3 color = mix(uShadowColor, uMidColor, clamp(quantized * 1.4, 0.0, 1.0));
    color = mix(color, uHighlightColor, clamp((quantized - 0.45) * 2.0, 0.0, 1.0));
    color = clamp(color, 0.0, 1.0);
    vec3 texColor = texture2D(uTexture, vTexCoord).rgb;
    gl_FragColor = vec4(mix(color, color * texColor, uTextureBlend), 1.0);
}
        ''',
        'parameters': {
            'shadow_color': dict(_color_param('Shadow color', (0.16, 0.18, 0.22)), uniform='uShadowColor'),
            'mid_color': dict(_color_param('Mid color', (0.58, 0.62, 0.68)), uniform='uMidColor'),
            'highlight_color': dict(_color_param('Highlight color', (1.0, 0.98, 0.94)), uniform='uHighlightColor'),
            'levels': _int_param('Band count', 4, 2, 12, uniform='uLevels'),
            'texture_blend': _float_param('Texture blend', 0.0, 0.0, 1.0, 0.05, uniform='uTextureBlend'),
        },
    },
    'Gooch': {
        'name': 'Gooch',
        'description': 'Technical illustration shading with adjustable warm/cool balance.',
        'vertex': '''
#version 120
varying vec3 vNormal;
varying vec3 vPosition;
varying vec2 vTexCoord;
uniform mat4 uProjectionMatrix;
uniform mat4 uModelViewMatrix;
uniform mat3 uNormalMatrix;

void main() {
    vNormal = normalize(uNormalMatrix * gl_Normal);
    vPosition = (uModelViewMatrix * gl_Vertex).xyz;
    vTexCoord = gl_MultiTexCoord0.st;
    gl_Position = uProjectionMatrix * uModelViewMatrix * gl_Vertex;
}
        ''',
        'fragment': '''
#version 120
varying vec3 vNormal;
varying vec3 vPosition;
varying vec2 vTexCoord;
uniform vec3 uCoolColor;
uniform vec3 uWarmColor;
uniform float uReflectionStrength;
uniform int uColorDepth;
uniform sampler2D uTexture;
uniform float uTextureBlend;

void main() {
    vec3 normal = normalize(vNormal);
    vec3 lightDir = normalize(vec3(1.0, 1.0, 1.0) - vPosition);
    float dotProduct = dot(normal, lightDir);
    float t = (dotProduct + 1.0) * 0.5;

    vec3 color = mix(uCoolColor, uWarmColor, clamp(t, 0.0, 1.0));
    color += vec3(uReflectionStrength * 0.25);
    float levels = max(float(uColorDepth), 2.0);
    color = floor(clamp(color, 0.0, 1.0) * levels) / levels;
    vec3 texColor = texture2D(uTexture, vTexCoord).rgb;
    gl_FragColor = vec4(mix(color, color * texColor, uTextureBlend), 1.0);
}
        ''',
        'parameters': {
            'cool_color': dict(_color_param('Cool color', (0.24, 0.28, 0.5)), uniform='uCoolColor'),
            'warm_color': dict(_color_param('Warm color', (0.9, 0.68, 0.16)), uniform='uWarmColor'),
            'reflection_strength': _float_param('Reflection', 0.7, 0.0, 2.0, 0.02, uniform='uReflectionStrength'),
            'color_depth': _int_param('Color depth', 10, 2, 24, uniform='uColorDepth'),
            'texture_blend': _float_param('Texture blend', 0.0, 0.0, 1.0, 0.05, uniform='uTextureBlend'),
        },
    },
    'Checkerboard': {
        'name': 'Checkerboard',
        'description': 'Procedural checker preview for UV and scale testing.',
        'vertex': '''
#version 120
varying vec2 vTexCoord;
uniform mat4 uProjectionMatrix;
uniform mat4 uModelViewMatrix;

void main() {
    vTexCoord = gl_MultiTexCoord0.xy;
    gl_Position = uProjectionMatrix * uModelViewMatrix * gl_Vertex;
}
        ''',
        'fragment': '''
#version 120
varying vec2 vTexCoord;
uniform vec3 uDarkColor;
uniform vec3 uLightColor;
uniform float uScale;

void main() {
    float checker = mod(floor(vTexCoord.x * uScale) + floor(vTexCoord.y * uScale), 2.0);
    vec3 color = mix(uDarkColor, uLightColor, checker);
    gl_FragColor = vec4(color, 1.0);
}
        ''',
        'parameters': {
            'dark_color': dict(_color_param('Dark color', (0.18, 0.18, 0.18)), uniform='uDarkColor'),
            'light_color': dict(_color_param('Light color', (0.92, 0.92, 0.92)), uniform='uLightColor'),
            'scale': _float_param('Pattern scale', 10.0, 1.0, 40.0, 0.5, uniform='uScale'),
        },
    },
    'Hatching': {
        'name': 'Cross-Hatching',
        'description': 'Illustration pass with adjustable ink color, paper color, and density.',
        'vertex': '''
#version 120
varying vec3 vNormal;
varying vec3 vPosition;
varying vec2 vTexCoord;
uniform mat4 uProjectionMatrix;
uniform mat4 uModelViewMatrix;
uniform mat3 uNormalMatrix;

void main() {
    vNormal = normalize(uNormalMatrix * gl_Normal);
    vPosition = (uModelViewMatrix * gl_Vertex).xyz;
    vTexCoord = gl_MultiTexCoord0.st;
    gl_Position = uProjectionMatrix * uModelViewMatrix * gl_Vertex;
}
        ''',
        'fragment': '''
#version 120
varying vec3 vNormal;
varying vec3 vPosition;
varying vec2 vTexCoord;
uniform vec3 uInkColor;
uniform vec3 uPaperColor;
uniform float uDensity;
uniform float uShadowThreshold;
uniform float uMidThreshold;
uniform sampler2D uTexture;
uniform float uTextureBlend;

void main() {
    vec3 normal = normalize(vNormal);
    vec3 lightDir = normalize(vec3(1.0, 1.0, 1.0) - vPosition);
    float intensity = clamp(dot(normal, lightDir), 0.0, 1.0);
    float patternA = mod((gl_FragCoord.x + gl_FragCoord.y) * uDensity, 2.0);
    float patternB = mod((gl_FragCoord.x - gl_FragCoord.y) * uDensity, 2.0);

    float inkMix = 0.0;
    if (intensity < uShadowThreshold) {
        inkMix = max(patternA, patternB);
    } else if (intensity < uMidThreshold) {
        inkMix = patternA;
    }

    vec3 color = mix(uPaperColor, uInkColor, clamp(inkMix, 0.0, 1.0));
    vec3 texColor = texture2D(uTexture, vTexCoord).rgb;
    gl_FragColor = vec4(mix(color, color * texColor, uTextureBlend), 1.0);
}
        ''',
        'parameters': {
            'ink_color': dict(_color_param('Ink color', (0.12, 0.12, 0.12)), uniform='uInkColor'),
            'paper_color': dict(_color_param('Paper color', (0.95, 0.94, 0.9)), uniform='uPaperColor'),
            'density': _float_param('Line density', 0.6, 0.1, 4.0, 0.05, uniform='uDensity'),
            'shadow_threshold': _float_param('Shadow threshold', 0.35, 0.0, 1.0, 0.01, uniform='uShadowThreshold'),
            'mid_threshold': _float_param('Mid threshold', 0.65, 0.0, 1.0, 0.01, uniform='uMidThreshold'),
            'texture_blend': _float_param('Texture blend', 0.0, 0.0, 1.0, 0.05, uniform='uTextureBlend'),
        },
    },
}


class ShaderProgram:
    """Encapsulates an OpenGL shader program."""

    def __init__(self, name, vertex_source, fragment_source):
        self.name = name
        self.vertex_source = vertex_source
        self.fragment_source = fragment_source
        self.program = None
        self.is_compiled = False
        self.uniform_locations = {}

    def compile(self):
        """Compile the shader program."""
        self.uniform_locations = {}
        if self.vertex_source is None or self.fragment_source is None:
            self.program = None
            self.is_compiled = True
            return True

        try:
            vertex = glCreateShader(GL_VERTEX_SHADER)
            glShaderSource(vertex, self.vertex_source)
            glCompileShader(vertex)

            if not glGetShaderiv(vertex, GL_COMPILE_STATUS):
                logger.error("Vertex shader compilation failed for %s:", self.name)
                logger.error(glGetShaderInfoLog(vertex).decode())
                glDeleteShader(vertex)
                return False

            fragment = glCreateShader(GL_FRAGMENT_SHADER)
            glShaderSource(fragment, self.fragment_source)
            glCompileShader(fragment)

            if not glGetShaderiv(fragment, GL_COMPILE_STATUS):
                logger.error("Fragment shader compilation failed for %s:", self.name)
                logger.error(glGetShaderInfoLog(fragment).decode())
                glDeleteShader(vertex)
                glDeleteShader(fragment)
                return False

            self.program = glCreateProgram()
            glAttachShader(self.program, vertex)
            glAttachShader(self.program, fragment)
            glLinkProgram(self.program)

            if not glGetProgramiv(self.program, GL_LINK_STATUS):
                logger.error("Shader program linking failed for %s:", self.name)
                logger.error(glGetProgramInfoLog(self.program).decode())
                glDeleteProgram(self.program)
                self.program = None
                glDeleteShader(vertex)
                glDeleteShader(fragment)
                return False

            glDeleteShader(vertex)
            glDeleteShader(fragment)

            self.is_compiled = True
            logger.info("Successfully compiled shader: %s", self.name)
            return True
        except Exception as exc:
            logger.error("Exception compiling shader %s: %s", self.name, exc)
            self.is_compiled = False
            return False

    def use(self):
        """Use this shader program."""
        if self.program is None:
            glUseProgram(0)
            return True
        glUseProgram(self.program)
        return True

    def get_uniform_location(self, uniform_name):
        """Get and cache a uniform location."""
        if self.program is None:
            return -1
        if uniform_name not in self.uniform_locations:
            self.uniform_locations[uniform_name] = glGetUniformLocation(self.program, uniform_name)
        return self.uniform_locations[uniform_name]

    def cleanup(self):
        """Clean up shader program."""
        if self.program is not None:
            glDeleteProgram(self.program)
        self.program = None
        self.is_compiled = False
        self.uniform_locations = {}


class ShaderManager:
    """Manages shader programs, availability, tuning, and selection."""

    def __init__(self, enabled_shaders=None, current_shader=None, parameter_values=None):
        self.shaders = {}
        self.current_shader = 'None'
        self.enabled_shaders = []
        self.parameter_values = {}
        self.scene_light_state = {
            'ambient': [0.2, 0.2, 0.2, 1.0],
            'diffuse': [0.8, 0.8, 0.8, 1.0],
            'specular': [1.0, 1.0, 1.0, 1.0],
            'position': [0.0, 0.0, 1.0, 1.0],
        }
        self.material_state = {
            'ambient': [0.2, 0.2, 0.2],
            'diffuse': [0.8, 0.8, 0.8],
            'specular': [1.0, 1.0, 1.0],
            'shininess': 32.0,
        }
        self.matrix_state = {
            'projection': Numeric.identity(4, Numeric.Float),
            'model_view': Numeric.identity(4, Numeric.Float),
            'normal': Numeric.identity(3, Numeric.Float),
        }
        self._load_shaders()
        self.set_enabled_shaders(enabled_shaders)
        self.set_parameter_values(parameter_values or {})
        self.set_current_shader(current_shader or 'None')

    def _shader_keys(self):
        return list(SHADERS.keys())

    def _load_shaders(self):
        for key, shader_def in SHADERS.items():
            self.shaders[key] = ShaderProgram(
                shader_def['name'],
                shader_def['vertex'],
                shader_def['fragment'],
            )

    def _normalize_color(self, value, default):
        if not isinstance(value, (list, tuple)) or len(value) < 3:
            value = default
        normalized = []
        for component in list(value)[:3]:
            component = float(component)
            if component > 1.0:
                component = component / 255.0
            normalized.append(max(0.0, min(1.0, component)))
        return normalized

    def _normalize_parameter_value(self, param_def, value):
        value_type = param_def.get('type')
        default = param_def.get('default')
        if value_type == 'color':
            return self._normalize_color(value, default)
        if value_type == 'int':
            try:
                normalized = int(round(float(value)))
            except (TypeError, ValueError):
                normalized = int(default)
            return max(int(param_def.get('min', normalized)), min(int(param_def.get('max', normalized)), normalized))
        if value_type == 'float':
            try:
                normalized = float(value)
            except (TypeError, ValueError):
                normalized = float(default)
            return max(float(param_def.get('min', normalized)), min(float(param_def.get('max', normalized)), normalized))
        if value_type == 'bool':
            return bool(value)
        return value if value is not None else default

    def _normalize_vec3(self, value, default):
        if not isinstance(value, (list, tuple)) or len(value) < 3:
            return list(default)
        normalized = []
        for component in list(value)[:3]:
            try:
                normalized.append(float(component))
            except (TypeError, ValueError):
                normalized.append(float(default[len(normalized)]))
        return normalized

    def _normalize_vec4(self, value, default):
        if not isinstance(value, (list, tuple)) or len(value) < 4:
            return list(default)
        normalized = []
        for component in list(value)[:4]:
            try:
                normalized.append(float(component))
            except (TypeError, ValueError):
                normalized.append(float(default[len(normalized)]))
        return normalized

    def set_scene_lighting(self, ambient=None, diffuse=None, specular=None, position=None):
        if ambient is not None:
            self.scene_light_state['ambient'] = self._normalize_vec4(ambient, self.scene_light_state['ambient'])
        if diffuse is not None:
            self.scene_light_state['diffuse'] = self._normalize_vec4(diffuse, self.scene_light_state['diffuse'])
        if specular is not None:
            self.scene_light_state['specular'] = self._normalize_vec4(specular, self.scene_light_state['specular'])
        if position is not None:
            self.scene_light_state['position'] = self._normalize_vec4(position, self.scene_light_state['position'])

    def set_material_state(self, ambient=None, diffuse=None, specular=None, shininess=None):
        if ambient is not None:
            self.material_state['ambient'] = self._normalize_vec3(ambient, self.material_state['ambient'])
        if diffuse is not None:
            self.material_state['diffuse'] = self._normalize_vec3(diffuse, self.material_state['diffuse'])
        if specular is not None:
            self.material_state['specular'] = self._normalize_vec3(specular, self.material_state['specular'])
        if shininess is not None:
            try:
                self.material_state['shininess'] = float(shininess)
            except (TypeError, ValueError):
                pass

    def sync_matrix_state_from_gl(self):
        try:
            projection = Numeric.array(glGetFloatv(GL_PROJECTION_MATRIX), Numeric.Float)
            model_view = Numeric.array(glGetFloatv(GL_MODELVIEW_MATRIX), Numeric.Float)
            try:
                normal = LinearAlgebra.inverse(model_view[:3, :3]).transpose()
            except Exception:
                normal = Numeric.identity(3, Numeric.Float)

            self.matrix_state['projection'] = projection
            self.matrix_state['model_view'] = model_view
            self.matrix_state['normal'] = Numeric.array(normal, Numeric.Float)
        except Exception:
            return

    def compile_all(self):
        success = True
        for shader in self.shaders.values():
            if not shader.compile():
                success = False
        return success

    def get_all_shader_list(self):
        return [(key, self.shaders[key].name) for key in self._shader_keys()]

    def get_shader_list(self):
        return [(key, self.shaders[key].name) for key in self._shader_keys() if key in self.enabled_shaders]

    def get_enabled_shaders(self):
        return list(self.enabled_shaders)

    def is_shader_enabled(self, shader_key):
        return shader_key in self.enabled_shaders

    def set_enabled_shaders(self, shader_keys):
        requested = []
        if shader_keys is None:
            requested = [key for key in self._shader_keys() if key != 'None']
        elif shader_keys:
            for shader_key in shader_keys:
                if shader_key in SHADERS and shader_key not in requested:
                    requested.append(shader_key)
        self.enabled_shaders = []
        for shader_key in self._shader_keys():
            if shader_key == 'None' or shader_key in requested:
                self.enabled_shaders.append(shader_key)
        if self.current_shader not in self.enabled_shaders:
            self.current_shader = 'None'

    def set_shader_enabled(self, shader_key, enabled):
        if shader_key not in SHADERS or shader_key == 'None':
            return shader_key == 'None'
        enabled_shaders = [key for key in self.enabled_shaders if key != 'None']
        if enabled and shader_key not in enabled_shaders:
            enabled_shaders.append(shader_key)
        if not enabled:
            enabled_shaders = [key for key in enabled_shaders if key != shader_key]
        self.set_enabled_shaders(enabled_shaders)
        return True

    def get_shader_parameters(self, shader_key):
        parameters = []
        shader_def = SHADERS.get(shader_key, {})
        for param_key, param_def in shader_def.get('parameters', {}).items():
            parameter = copy.deepcopy(param_def)
            parameter['key'] = param_key
            parameter['value'] = self.get_parameter_value(shader_key, param_key)
            parameters.append(parameter)
        return parameters

    def get_parameter_value(self, shader_key, param_key):
        shader_values = self.parameter_values.get(shader_key, {})
        if param_key in shader_values:
            return copy.deepcopy(shader_values[param_key])
        shader_def = SHADERS.get(shader_key, {})
        param_def = shader_def.get('parameters', {}).get(param_key, {})
        return copy.deepcopy(param_def.get('default'))

    def set_parameter_value(self, shader_key, param_key, value):
        shader_def = SHADERS.get(shader_key, {})
        param_def = shader_def.get('parameters', {}).get(param_key)
        if not param_def:
            return False
        normalized = self._normalize_parameter_value(param_def, value)
        self.parameter_values.setdefault(shader_key, {})[param_key] = normalized
        return True

    def set_parameter_values(self, values):
        self.parameter_values = {}
        if not values or not hasattr(values, 'items'):
            return
        for shader_key, shader_values in values.items():
            if shader_key not in SHADERS or not hasattr(shader_values, 'items'):
                continue
            for param_key, param_value in shader_values.items():
                self.set_parameter_value(shader_key, param_key, param_value)

    def reset_shader_parameters(self, shader_key):
        if shader_key in self.parameter_values:
            del self.parameter_values[shader_key]

    def reset_all_parameters(self):
        self.parameter_values = {}

    def set_current_shader(self, shader_key):
        if shader_key not in self.shaders:
            return False
        if shader_key != 'None' and shader_key not in self.enabled_shaders:
            self.set_shader_enabled(shader_key, True)
        self.current_shader = shader_key if shader_key in self.enabled_shaders else 'None'
        return True

    def _apply_uniform(self, shader, uniform_name, value):
        location = shader.get_uniform_location(uniform_name)
        if location < 0:
            return
        if isinstance(value, (list, tuple)):
            if len(value) == 3:
                glUniform3f(location, float(value[0]), float(value[1]), float(value[2]))
            elif len(value) == 4:
                glUniform4f(location, float(value[0]), float(value[1]), float(value[2]), float(value[3]))
            return
        if isinstance(value, bool):
            glUniform1i(location, int(value))
        elif isinstance(value, int):
            glUniform1i(location, value)
        else:
            glUniform1f(location, float(value))

    def _apply_shader_uniforms(self, shader_key, shader):
        texture_loc = shader.get_uniform_location('uTexture')
        if texture_loc >= 0:
            glUniform1i(texture_loc, 0)

        projection_loc = shader.get_uniform_location('uProjectionMatrix')
        if projection_loc >= 0:
            glUniformMatrix4fv(projection_loc, 1, GL_FALSE, self.matrix_state['projection'])
        model_view_loc = shader.get_uniform_location('uModelViewMatrix')
        if model_view_loc >= 0:
            glUniformMatrix4fv(model_view_loc, 1, GL_FALSE, self.matrix_state['model_view'])
        normal_loc = shader.get_uniform_location('uNormalMatrix')
        if normal_loc >= 0:
            glUniformMatrix3fv(normal_loc, 1, GL_FALSE, self.matrix_state['normal'])

        # Runtime scene/material uniforms used by modernized shaders.
        self._apply_uniform(shader, 'uSceneAmbient', self.scene_light_state['ambient'])
        self._apply_uniform(shader, 'uSceneDiffuse', self.scene_light_state['diffuse'])
        self._apply_uniform(shader, 'uSceneSpecular', self.scene_light_state['specular'])
        self._apply_uniform(shader, 'uLightPosition', self.scene_light_state['position'])
        self._apply_uniform(shader, 'uMaterialAmbient', self.material_state['ambient'])
        self._apply_uniform(shader, 'uMaterialDiffuse', self.material_state['diffuse'])
        self._apply_uniform(shader, 'uMaterialSpecular', self.material_state['specular'])
        self._apply_uniform(shader, 'uMaterialShininess', self.material_state['shininess'])

        shader_def = SHADERS.get(shader_key, {})
        for param_key, param_def in shader_def.get('parameters', {}).items():
            uniform_name = param_def.get('uniform')
            if not uniform_name:
                continue
            value = self.get_parameter_value(shader_key, param_key)
            self._apply_uniform(shader, uniform_name, value)

    def apply_render_state(self):
        shader_key = self.current_shader or 'None'
        shader_def = SHADERS.get(shader_key, {})
        render_state = shader_def.get('render_state')
        if not render_state:
            return False
        try:
            glPushAttrib(GL_POLYGON_BIT | GL_LINE_BIT)
            if render_state.get('polygon_mode') == 'line':
                glPolygonMode(GL_FRONT_AND_BACK, GL_LINE)
            line_width_param = render_state.get('line_width_param')
            if line_width_param:
                glLineWidth(float(self.get_parameter_value(shader_key, line_width_param)))
            return True
        except Exception as exc:
            logger.debug('Unable to apply shader render state: %s', exc)
            return False

    def restore_render_state(self, applied):
        if not applied:
            return
        try:
            glPopAttrib()
        except Exception as exc:
            logger.debug('Unable to restore shader render state: %s', exc)

    def use_current_shader(self):
        shader_key = self.current_shader or 'None'
        if shader_key not in self.shaders or shader_key == 'None':
            glUseProgram(0)
            return False
        shader = self.shaders[shader_key]
        if shader.program is None:
            glUseProgram(0)
            return False
        shader.use()
        self._apply_shader_uniforms(shader_key, shader)
        return True

    def get_current_shader(self):
        return self.current_shader or 'None'

    def get_shader_description(self, shader_key):
        if shader_key in SHADERS:
            return SHADERS[shader_key].get('description', '')
        return ''

    def serialize_state(self):
        return {
            'enabled_shaders': list(self.enabled_shaders),
            'current_shader': self.get_current_shader(),
            'parameter_values': copy.deepcopy(self.parameter_values),
        }

    def configure(self, enabled_shaders=None, current_shader=None, parameter_values=None):
        self.set_enabled_shaders(enabled_shaders)
        self.set_parameter_values(parameter_values or {})
        self.set_current_shader(current_shader or 'None')

    def cleanup(self):
        for shader in self.shaders.values():
            shader.cleanup()