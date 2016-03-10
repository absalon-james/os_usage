from magic_the_decorating.decorator import Base as BaseDecorator


class _RouterDecorator(BaseDecorator):
    """Callable that alters cinder's v2 router.

    Adds the usage endpoint.
    """
    def __init__(self):
        """Calls parent class init and sets signature."""
        super(_RouterDecorator, self).__init__('__cinder_router_decorator__')

    def setup_routes(self, module, config):
        """Adds the usage api endpoint to routes.

        :param module: Python module containing APIRouter class
        :param config: Dict - unused at this point.
        :returns: Modified Module
        """
        import usage
        klass_name = 'APIRouter'
        method_name = '_setup_routes'

        klass = getattr(module, klass_name, None)
        if klass is None:
            return module

        old_setup_routes = getattr(klass, method_name, None)

        def new_setup_routes(api_router_self, mapper, ext_mgr):
            """Wrapper for old_setup_routes."""
            old_setup_routes(api_router_self, mapper, ext_mgr)

            api_router_self.resources['usages'] = \
                usage.create_resource(ext_mgr)
            mapper.resource("usage", "usages",
                            controller=api_router_self.resources['usages'])

        setattr(klass, method_name, new_setup_routes)
        return module

    def _decorate(self, module, config):
        """Calls the setup routes method."""
        return self.setup_routes(module, config)

RouterDecorator = _RouterDecorator()
