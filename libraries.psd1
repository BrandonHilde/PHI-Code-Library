# The libraries build.ps1 knows about. A library comes after everything in its Uses.
# Its main file is Folder\Name.phi, and programs include it with `use Name;`.
@{
	Libraries = @(
		@{ Name = 'corelib'; Folder = 'libs\core'; Uses = @() }
		@{ Name = 'imagelib'; Folder = 'libs\image'; Uses = @('corelib') }
		@{ Name = 'fontlib'; Folder = 'libs\font'; Uses = @('corelib') }
		@{ Name = 'editlib'; Folder = 'libs\edit'; Uses = @() }
		@{ Name = 'vectorlib'; Folder = 'libs\vector'; Uses = @() }
		@{ Name = 'medialib'; Folder = 'libs\media'; Uses = @() }
		@{ Name = 'weblib'; Folder = 'libs\web'; Uses = @('corelib', 'vectorlib', 'medialib') }
		@{ Name = 'encodinglib'; Folder = 'libs\encoding'; Uses = @() }
		@{ Name = 'netlib'; Folder = 'libs\net'; Uses = @('corelib') }
	)
}
